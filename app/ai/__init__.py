from functools import lru_cache

from app.ai.base import AIProvider
from app.config import get_settings


@lru_cache
def get_ai_provider() -> AIProvider:
    """환경변수로 provider 선택. 라우터에서는 Depends(get_ai_provider)로 주입."""
    settings = get_settings()
    if settings.mock_ai:
        from app.ai.mock import MockProvider

        return MockProvider()
    # 실제 provider(안뇽GPT Gateway / Gemini 직접 호출)는 5단계에서 구현
    raise NotImplementedError("실제 AI provider는 아직 구현되지 않았습니다. MOCK_AI=true로 실행하세요.")


__all__ = ["AIProvider", "get_ai_provider"]
