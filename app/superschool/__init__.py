"""슈퍼스쿨 연동 (OAuth 2.0 인가 코드 방식 가정).

슈퍼스쿨은 외부 서비스용 API를 공개하지 않아서, "API를 받았다면 이렇게 붙는다"를 구현해 둔다.
- SUPERSCHOOL_MOCK=true (기본): MockSuperschool. 정해진 가짜 계정·학사 일정을 돌려준다.
- SUPERSCHOOL_MOCK=false: OAuthSuperschool. .env의 client_id·secret·주소로 실제 OAuth 서버에 붙는다.
  응답 필드 이름은 가정한 것이라, 실제 문서를 받으면 oauth.py의 _profile/_event 변환만 고치면 된다.
"""
from functools import lru_cache

from app.config import get_settings
from app.superschool.base import SchoolEvent, SuperschoolClient, SuperschoolError, SuperschoolProfile, Tokens

__all__ = ["SchoolEvent", "SuperschoolClient", "SuperschoolError", "SuperschoolProfile", "Tokens",
           "get_superschool_client"]


@lru_cache
def get_superschool_client() -> SuperschoolClient:
    s = get_settings()
    if s.superschool_mock:
        from app.superschool.mock import MockSuperschool

        return MockSuperschool()
    missing = [name for name, value in [
        ("SUPERSCHOOL_CLIENT_ID", s.superschool_client_id), ("SUPERSCHOOL_CLIENT_SECRET", s.superschool_client_secret),
        ("SUPERSCHOOL_AUTHORIZE_URL", s.superschool_authorize_url), ("SUPERSCHOOL_TOKEN_URL", s.superschool_token_url),
        ("SUPERSCHOOL_API_BASE_URL", s.superschool_api_base_url),
    ] if not value]
    if missing:
        raise RuntimeError(f"SUPERSCHOOL_MOCK=false인데 {', '.join(missing)}가 비어 있습니다.")
    from app.superschool.oauth import OAuthSuperschool

    return OAuthSuperschool(
        client_id=s.superschool_client_id, client_secret=s.superschool_client_secret,
        authorize_url=s.superschool_authorize_url, token_url=s.superschool_token_url,
        api_base_url=s.superschool_api_base_url, scope=s.superschool_scope,
    )
