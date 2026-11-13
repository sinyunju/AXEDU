"""Gateway provider 단위 테스트 (네트워크 없이 httpx.MockTransport 사용)."""
import asyncio
import base64
import json
import logging

import httpx
import pytest

from app.ai import AIError
from app.ai.gateway import GatewayImageProvider, GatewayTextProvider, parse_json_object

BASE = "https://api.example.test/v1/gateway"
GOOD = {
    "easy_sentences": ["식물은 햇빛으로 양분을 만들어요."],
    "hard_words": [{"word": "광합성", "meaning": "식물이 양분을 만드는 일"}],
    "image_suggestion": {"needed": False, "reason": "", "prompt": ""},
}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200  # base64가 로그 절단 기준(80자)보다 길게


def completion(content: str) -> dict:
    return {
        "id": "c1", "object": "chat.completion", "created": 0, "model": "m",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
    }


def text_provider(handler) -> GatewayTextProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GatewayTextProvider(base_url=BASE, api_key="k", model_fast="fast", model_main="main", http_client=client)


@pytest.mark.parametrize("raw", [
    json.dumps(GOOD),
    "```json\n" + json.dumps(GOOD) + "\n```",
    "다음은 결과입니다:\n" + json.dumps(GOOD) + "\n끝",
])
def test_parse_json_object(raw):
    assert parse_json_object(raw) == GOOD


@pytest.mark.parametrize("raw", ["", None, "[1,2]", "그냥 문장"])
def test_parse_json_object_rejects(raw):
    with pytest.raises(ValueError):
        parse_json_object(raw)


def test_restructure_sends_schema_and_parses():
    requests = []

    def handler(req: httpx.Request):
        requests.append(req)
        return httpx.Response(200, json=completion(json.dumps(GOOD, ensure_ascii=False)))

    result = asyncio.run(text_provider(handler).restructure_page("광합성은 ..."))
    assert result == GOOD
    req = requests[0]
    assert str(req.url) == f"{BASE}/chat/completions"
    assert req.headers["authorization"] == "Bearer k" and req.headers["user-agent"] == "easyclass-backend/0.1"
    body = json.loads(req.content)
    assert body["model"] == "main"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert "광합성은 ..." in body["messages"][-1]["content"]


def test_retries_once_on_bad_json_then_fails():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(200, json=completion("JSON 아님" if len(calls) == 1 else json.dumps(GOOD)))

    assert asyncio.run(text_provider(handler).restructure_page("x")) == GOOD
    assert len(calls) == 2

    calls.clear()
    bad = text_provider(lambda req: (calls.append(1), httpx.Response(200, json=completion('{"easy_sentences": []}')))[1])
    with pytest.raises(AIError):
        asyncio.run(bad.restructure_page("x"))
    assert len(calls) == 2  # 1회 재시도 후 에러


def test_falls_back_when_json_schema_rejected():
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": {"message": "response_format not supported"}})
        return httpx.Response(200, json=completion(json.dumps(GOOD)))

    p = text_provider(handler)
    assert asyncio.run(p.restructure_page("x")) == GOOD
    assert asyncio.run(p.restructure_page("y")) == GOOD
    # 첫 호출만 schema 시도, 이후에는 바로 프롬프트 기반
    assert ["response_format" in b for b in bodies] == [True, False, False]


def test_api_error_becomes_ai_error():
    p = text_provider(lambda req: httpx.Response(401, json={"error": {"message": "bad key"}}))
    with pytest.raises(AIError):
        asyncio.run(p.restructure_page("x"))


# ---------- 이미지 ----------
def image_provider(handler) -> GatewayImageProvider:
    return GatewayImageProvider(base_url=BASE, api_key="secret-key", model="gemini-nano-banana-2.1",
                                image_size="1K", aspect_ratio="1:1", transport=httpx.MockTransport(handler))


def test_image_data_uri_and_request_format(caplog):
    seen = []

    def handler(req):
        seen.append(req)
        data_uri = "data:image/png;base64," + base64.b64encode(PNG).decode()
        return httpx.Response(200, json={"id": "img-1", "created": 0, "model": "m",
                                         "data": [{"url": data_uri}], "credits_charged": 37})

    caplog.set_level(logging.INFO, logger="app.ai.gateway")
    p = image_provider(handler)
    assert asyncio.run(p.generate_image("잎 그림")) == PNG

    req = seen[0]
    assert req.method == "POST" and str(req.url) == f"{BASE}/images/generate/"
    assert req.headers["authorization"] == "Bearer secret-key" and req.headers["user-agent"]
    body = json.loads(req.content)
    assert body["model"] == "gemini-nano-banana-2.1" and body["number_of_images"] == 1
    assert body["aspect_ratio"] == "1:1" and body["image_size"] == "1K"
    assert body["prompt"].startswith("잎 그림") and "글자" in body["prompt"]

    # 첫 응답 구조가 로그에 남되 base64 전체는 남지 않음
    logs = [r.getMessage() for r in caplog.records if "응답 구조" in r.getMessage()]
    assert len(logs) == 1 and "credits_charged" in logs[0] and "<str len=" in logs[0]
    asyncio.run(p.generate_image("두 번째"))
    assert len([r for r in caplog.records if "응답 구조" in r.getMessage()]) == 1  # 첫 호출만


def test_image_http_url_is_downloaded_without_api_key():
    seen = []

    def handler(req):
        seen.append(req)
        if req.url.host == "cdn.example.test":
            return httpx.Response(200, content=PNG)
        return httpx.Response(200, json={"data": [{"url": "https://cdn.example.test/a.png"}]})

    assert asyncio.run(image_provider(handler).generate_image("x")) == PNG
    cdn_req = seen[1]
    assert "authorization" not in cdn_req.headers  # 외부 CDN에 키를 보내지 않음


@pytest.mark.parametrize("response", [
    httpx.Response(500, text="internal"),
    httpx.Response(403, text="error code: 1010"),
    httpx.Response(200, text="not json"),
    httpx.Response(200, json={"data": []}),
    httpx.Response(200, json={"data": [{"unknown": "x"}]}),
    httpx.Response(200, json={"data": [{"url": "data:image/png;base64," + base64.b64encode(b"hello").decode()}]}),
    httpx.Response(200, json={"operation_id": "op1", "status": "processing"}),
])
def test_image_errors(response):
    with pytest.raises(AIError):
        asyncio.run(image_provider(lambda req: response).generate_image("x"))


def test_live_caption_uses_fast_model_and_previous():
    bodies = []
    out = {"easy_transcript": ["이전 자막이에요.", "새 자막이에요."], "hard_words": []}

    def handler(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200, json=completion(json.dumps(out, ensure_ascii=False)))

    result = asyncio.run(text_provider(handler).live_caption("페이지 글", "선생님 발화", ["이전 자막이에요."]))
    assert result == out
    body = bodies[0]
    assert body["model"] == "fast"  # 실시간은 MODEL_FAST
    assert body["response_format"]["json_schema"]["name"] == "live_caption"
    prompt = body["messages"][-1]["content"]
    assert "- 이전 자막이에요." in prompt and "선생님 발화" in prompt and "페이지 글" in prompt
