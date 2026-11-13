"""안뇽GPT API Gateway provider.

- 텍스트: OpenAI 호환 Chat Completions (openai SDK, base_url만 교체)
- 이미지: Gateway 전용 POST {base_url}/images/generate/ (httpx 직접 호출)
"""
import base64
import json
import logging
import re
from typing import Any

import httpx
from openai import APIError, AsyncOpenAI, BadRequestError
from pydantic import BaseModel, ValidationError

from app.ai.base import AIError, AIProvider, ImageProvider, image_extension
from app.ai.prompts import IMAGE_STYLE_SUFFIX, live_caption_messages, restructure_messages
from app.ai.schemas import LIVE_CAPTION_SCHEMA, RESTRUCTURE_SCHEMA, LiveCaptionOut, RestructureOut

logger = logging.getLogger(__name__)

# Gateway는 User-Agent가 비어 있으면 403(error code 1010)
USER_AGENT = "easyclass-backend/0.1"

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_object(text: str | None) -> dict[str, Any]:
    """모델 출력에서 JSON 객체를 꺼낸다. 코드블록·앞뒤 잡음은 허용."""
    if not text:
        raise ValueError("빈 응답")
    cleaned = _FENCE.sub("", text.strip()).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(cleaned[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("JSON 객체가 아님")
    return data


class GatewayTextProvider(AIProvider):
    name = "gateway"

    def __init__(self, *, base_url: str, api_key: str, model_fast: str, model_main: str,
                 timeout: float = 90, http_client: httpx.AsyncClient | None = None):
        self.client = AsyncOpenAI(
            base_url=base_url, api_key=api_key, timeout=timeout, max_retries=2,
            default_headers={"User-Agent": USER_AGENT}, http_client=http_client,
        )
        self.model_fast = model_fast
        self.model_main = model_main
        # json_schema response_format을 모델이 거부하면(400) 이후로는 프롬프트만으로 JSON을 요구
        self._schema_supported: dict[str, bool] = {}

    async def _complete(self, model: str, messages: list[dict[str, str]], response_format: dict | None) -> str | None:
        use_schema = response_format is not None and self._schema_supported.get(model, True)
        kwargs: dict[str, Any] = {"model": model, "messages": messages}
        if use_schema:
            kwargs["response_format"] = response_format
        try:
            resp = await self.client.chat.completions.create(**kwargs)
        except BadRequestError as e:
            if not use_schema:
                raise
            logger.warning("모델 %s가 json_schema를 거부해 프롬프트 기반 JSON으로 전환: %s", model, e)
            self._schema_supported[model] = False
            resp = await self.client.chat.completions.create(model=model, messages=messages)
        return resp.choices[0].message.content if resp.choices else None

    async def _json_call(self, model: str, messages: list[dict[str, str]], response_format: dict | None,
                         out_model: type[BaseModel]) -> dict[str, Any]:
        """JSON 응답 요청 → 파싱·검증. 실패하면 1회 재시도 후 AIError."""
        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                content = await self._complete(model, messages, response_format)
            except APIError as e:
                raise AIError(f"AI 호출 실패: {e}") from e
            try:
                return out_model.model_validate(parse_json_object(content)).model_dump()
            except (ValueError, ValidationError) as e:
                last_error = e
                logger.warning("JSON 파싱 실패(%d/2, model=%s): %s | 응답 앞부분=%r", attempt, model, e, (content or "")[:300])
        raise AIError(f"AI 응답 형식이 올바르지 않습니다: {last_error}")

    async def restructure_page(self, source_text: str) -> dict[str, Any]:
        return await self._json_call(self.model_main, restructure_messages(source_text), RESTRUCTURE_SCHEMA, RestructureOut)

    async def live_caption(self, source_text: str, transcript: str, previous_easy: list[str]) -> dict[str, Any]:
        # 실시간이라 빠른 모델 사용
        return await self._json_call(self.model_fast, live_caption_messages(source_text, transcript, previous_easy),
                                     LIVE_CAPTION_SCHEMA, LiveCaptionOut)

    async def generate_quiz(self, pages, transcripts) -> dict[str, Any]:
        raise NotImplementedError("8단계에서 구현")

    async def chat(self, pages, transcripts, history, message) -> dict[str, Any]:
        raise NotImplementedError("9단계에서 구현")


def describe_structure(value: Any, depth: int = 0) -> Any:
    """로그용: 응답 구조만 남기고 긴 문자열(base64 등)은 잘라낸다."""
    if depth > 5:
        return "…"
    if isinstance(value, dict):
        return {k: describe_structure(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [describe_structure(v, depth + 1) for v in value[:3]] + (["…"] if len(value) > 3 else [])
    if isinstance(value, str) and len(value) > 80:
        return f"<str len={len(value)} head={value[:40]!r}>"
    return value


class GatewayImageProvider(ImageProvider):
    name = "gateway"

    def __init__(self, *, base_url: str, api_key: str, model: str, image_size: str, aspect_ratio: str,
                 timeout: float = 90, transport: httpx.AsyncBaseTransport | None = None):
        self.url = base_url.rstrip("/") + "/images/generate/"
        self.model = model
        self.image_size = image_size
        self.aspect_ratio = aspect_ratio
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10),
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": USER_AGENT},
            transport=transport,
        )
        self._transport = transport
        self._structure_logged = False

    async def generate_image(self, prompt: str) -> bytes:
        body = {
            "model": self.model,
            "prompt": prompt.strip() + IMAGE_STYLE_SUFFIX,
            "number_of_images": 1,
            "aspect_ratio": self.aspect_ratio,
            "image_size": self.image_size,
        }
        try:
            resp = await self._client.post(self.url, json=body)
        except httpx.HTTPError as e:
            raise AIError(f"이미지 생성 요청 실패: {e!r}") from e
        if resp.status_code >= 400:
            raise AIError(f"이미지 생성 실패 (HTTP {resp.status_code}): {resp.text[:500]}")
        try:
            data = resp.json()
        except ValueError as e:
            raise AIError(f"이미지 응답이 JSON이 아닙니다: {resp.text[:200]!r}") from e

        # 문서에 정확한 응답 예시가 없어 첫 실제 응답의 구조를 로그로 남긴다 (base64는 잘라서)
        if not self._structure_logged:
            logger.info("이미지 생성 응답 구조(첫 호출): %s",
                        json.dumps(describe_structure(data), ensure_ascii=False))
            self._structure_logged = True
        try:
            image = await self._extract_image(data)
            if image_extension(image) is None:
                raise AIError(f"이미지 형식을 알 수 없습니다 (앞 8바이트={image[:8]!r})")
            return image
        except AIError:
            logger.error("이미지 응답 파싱 실패. 구조: %s", json.dumps(describe_structure(data), ensure_ascii=False))
            raise

    async def _extract_image(self, data: dict[str, Any]) -> bytes:
        if data.get("operation_id") and not data.get("data"):
            # Fal 계열의 지연 응답. 현재 기본 모델(Google)은 동기 응답이라 미지원.
            raise AIError(f"지연 응답(operation_id)은 지원하지 않습니다: status={data.get('status')}")
        items = data.get("data")
        if not isinstance(items, list) or not items:
            raise AIError("이미지 응답에 data 배열이 없습니다")
        item = items[0]
        if isinstance(item, str):
            return self._decode_b64(item)
        if not isinstance(item, dict):
            raise AIError("이미지 응답 data[0] 형식을 알 수 없습니다")
        # 문서 기준: Google은 data[0].url 에 data URI. 그 밖의 흔한 필드도 대비.
        for key in ("url", "b64_json", "base64", "image", "image_base64", "bytesBase64Encoded"):
            value = item.get(key)
            if not isinstance(value, str) or not value:
                continue
            if value.startswith(("http://", "https://")):
                return await self._download(value)
            return self._decode_b64(value)
        raise AIError(f"이미지 데이터 필드를 찾지 못했습니다: keys={list(item)}")

    @staticmethod
    def _decode_b64(value: str) -> bytes:
        if value.startswith("data:"):
            value = value.split(",", 1)[1] if "," in value else ""
        try:
            return base64.b64decode(value, validate=False)
        except (ValueError, TypeError) as e:
            raise AIError("이미지 base64 디코딩 실패") from e

    async def _download(self, url: str) -> bytes:
        # 외부 CDN URL에 Gateway 키가 새지 않도록 인증 헤더 없는 별도 클라이언트 사용
        try:
            async with httpx.AsyncClient(timeout=self._client.timeout, headers={"User-Agent": USER_AGENT},
                                         transport=self._transport) as plain:
                r = await plain.get(url)
                r.raise_for_status()
                return r.content
        except httpx.HTTPError as e:
            raise AIError(f"이미지 다운로드 실패: {e!r}") from e
