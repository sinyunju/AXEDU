"""실제 Gateway 연결 확인용 (서버 없이 단독 실행).

  .venv/bin/python -m scripts.ai_smoke            # 텍스트(페이지 재구성) 1회만 호출
  .venv/bin/python -m scripts.ai_smoke --image    # + 이미지 1장 생성 (약 37크레딧 소모)

.env의 MOCK_AI/MOCK_IMAGE 값과 관계없이 실제 provider를 사용한다. AI_API_KEY 필요.
이미지 응답 구조는 로그(INFO "이미지 생성 응답 구조")로 출력되고, 결과 파일은 storage/smoke/ 에 저장된다.
"""
import argparse
import asyncio
import json
import logging
import time

from app.ai.base import image_extension
from app.config import get_settings
from app.storage import save_file

SAMPLE = "1. 광합성이란?\n식물이 빛 에너지를 이용하여 이산화탄소와 물로 포도당을 합성하는 과정이다. 이 과정은 엽록체에서 일어난다."


async def main(with_image: bool) -> None:
    from app.ai.gateway import GatewayImageProvider, GatewayTextProvider

    s = get_settings()
    if not s.ai_api_key:
        raise SystemExit("AI_API_KEY가 비어 있습니다. .env에 키를 넣어 주세요.")

    text = GatewayTextProvider(base_url=s.ai_base_url, api_key=s.ai_api_key, model_live=s.model_live or s.model_main,
                               model_main=s.model_main, timeout=s.ai_timeout_seconds)
    print(f"[텍스트] model={s.model_main} 호출 중...")
    t0 = time.perf_counter()
    result = await text.restructure_page(SAMPLE)
    print(f"[텍스트] {time.perf_counter() - t0:.1f}s\n{json.dumps(result, ensure_ascii=False, indent=2)}")

    if not with_image:
        print("\n이미지는 건너뜀 (--image 로 실행하면 1장 생성, 약 37크레딧)")
        return
    prompt = result["image_suggestion"]["prompt"] or "잎에 햇빛이 비치고 뿌리로 물이 올라가는 식물"
    image = GatewayImageProvider(base_url=s.ai_base_url, api_key=s.ai_api_key, model=s.model_image,
                                 image_size=s.image_size, aspect_ratio=s.image_aspect_ratio,
                                 timeout=s.ai_timeout_seconds)
    print(f"\n[이미지] model={s.model_image} size={s.image_size} 호출 중... prompt={prompt!r}")
    t0 = time.perf_counter()
    data = await image.generate_image(prompt)
    rel = save_file("smoke", data, image_extension(data) or "bin")
    print(f"[이미지] {time.perf_counter() - t0:.1f}s, {len(data):,} bytes → {s.storage_dir / rel}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", action="store_true", help="이미지 1장도 생성 (크레딧 소모)")
    asyncio.run(main(parser.parse_args().image))
