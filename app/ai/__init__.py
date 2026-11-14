from functools import lru_cache

from app.ai.base import AIError, AIProvider, ImageProvider
from app.config import get_settings


def _require_key() -> str:
    key = get_settings().ai_api_key
    if not key:
        raise RuntimeError("AI_API_KEY가 비어 있습니다. .env에 키를 넣거나 MOCK_AI=true / MOCK_IMAGE=true로 실행하세요.")
    return key


@lru_cache
def get_ai_provider() -> AIProvider:
    """텍스트 LLM provider (MOCK_AI). 라우터에서는 Depends(get_ai_provider)로 주입."""
    s = get_settings()
    if s.mock_ai:
        from app.ai.mock import MockProvider

        return MockProvider()
    from app.ai.gateway import GatewayTextProvider

    return GatewayTextProvider(base_url=s.ai_base_url, api_key=_require_key(), model_live=s.model_live or s.model_main,
                               model_main=s.model_main, timeout=s.ai_timeout_seconds)


@lru_cache
def get_image_provider() -> ImageProvider:
    """이미지 생성 provider (MOCK_IMAGE). MOCK_AI와 독립적으로 동작."""
    s = get_settings()
    if s.mock_image:
        from app.ai.mock import MockImageProvider

        return MockImageProvider()
    from app.ai.gateway import GatewayImageProvider

    return GatewayImageProvider(base_url=s.ai_base_url, api_key=_require_key(), model=s.model_image,
                                image_size=s.image_size, aspect_ratio=s.image_aspect_ratio,
                                timeout=s.ai_timeout_seconds)


__all__ = ["AIError", "AIProvider", "ImageProvider", "get_ai_provider", "get_image_provider"]
