"""목 슈퍼스쿨: 실제 서버 없이 OAuth 흐름 전체를 흉내 낸다.

로그인 화면은 프론트의 개발용 화면(/auth/superschool/mock)을 쓰고, 그 화면이 돌려주는 code를 받는다.
  mock:student → 학생 "지우" / mock:teacher → 교사 "김하늘" (슈퍼스쿨로 로그인)
  mock:link    → 지금 로그인한 계정과 같은 사람이라고 가정한 계정 (계정 연결)
토큰은 "mock-token:<base64 JSON 프로필>" 형태라 서버를 다시 켜도 그대로 쓸 수 있다.
"""
import base64
import json
import secrets
from datetime import date, timedelta
from urllib.parse import urlencode, urlsplit

from app.models import Role
from app.superschool.base import SchoolEvent, SuperschoolClient, SuperschoolError, SuperschoolProfile, Tokens

SCHOOL = "천천중학교"
_LOGIN_PROFILES = {
    "mock:student": SuperschoolProfile("mock-student-jiwoo", "지우", Role.student, f"{SCHOOL} 2학년 3반"),
    "mock:teacher": SuperschoolProfile("mock-teacher-haneul", "김하늘", Role.teacher, f"{SCHOOL} · 과학과"),
}
# 오늘 기준 며칠 뒤 (시작, 끝, 제목, 분류)
_EVENTS = [
    (0, None, "동아리 활동", "행사"),
    (1, 4, "학부모 상담 주간", "행사"),
    (5, None, "재량휴업일", "휴업일"),
    (8, None, "진로 체험학습", "행사"),
    (12, 14, "2학기 기말고사", "시험"),
    (19, None, "학교 축제", "행사"),
]


def _encode(p: SuperschoolProfile) -> str:
    raw = json.dumps({"id": p.superschool_id, "name": p.name, "role": p.role.value, "school": p.school},
                     ensure_ascii=False)
    return "mock-token:" + base64.urlsafe_b64encode(raw.encode()).decode()


def _decode(token: str) -> SuperschoolProfile:
    try:
        if not token.startswith("mock-token:"):
            raise ValueError
        d = json.loads(base64.urlsafe_b64decode(token.removeprefix("mock-token:")))
        return SuperschoolProfile(d["id"], d["name"], Role(d["role"]), d["school"])
    except (ValueError, KeyError, json.JSONDecodeError):
        raise SuperschoolError("슈퍼스쿨 토큰이 올바르지 않습니다")


class MockSuperschool(SuperschoolClient):
    name = "mock"

    def authorize_url(self, *, redirect_uri: str, state: str, mode: str, role: Role | None) -> str:
        # 프론트(redirect_uri와 같은 주소)의 개발용 연동 화면으로 보냄
        parts = urlsplit(redirect_uri)
        query = {"mode": mode, "state": state, **({"role": role.value} if role else {})}
        return f"{parts.scheme}://{parts.netloc}/auth/superschool/mock?{urlencode(query)}"

    async def exchange_code(self, code: str, redirect_uri: str, *, role_hint: Role | None = None) -> Tokens:
        if code in _LOGIN_PROFILES:
            profile = _LOGIN_PROFILES[code]
        elif code == "mock:link" and role_hint is not None:
            # 계정 연결: 연결할 때마다 다른 슈퍼스쿨 계정(같은 사람이라고 가정)을 만든다
            uid = secrets.token_hex(4)
            profile = (SuperschoolProfile(f"mock-link-{uid}", "슈퍼스쿨 학생", Role.student, f"{SCHOOL} 2학년 3반")
                       if role_hint == Role.student else
                       SuperschoolProfile(f"mock-link-{uid}", "슈퍼스쿨 선생님", Role.teacher, f"{SCHOOL} · 과학과"))
        else:
            raise SuperschoolError("슈퍼스쿨 인증 코드가 올바르지 않습니다")
        return Tokens(access_token=_encode(profile), refresh_token=None, expires_at=None)

    async def refresh(self, refresh_token: str) -> Tokens:
        raise SuperschoolError("목 토큰은 만료되지 않습니다")

    async def get_profile(self, access_token: str) -> SuperschoolProfile:
        return _decode(access_token)

    async def get_events(self, access_token: str, start: date, end: date) -> list[SchoolEvent]:
        _decode(access_token)  # 토큰 확인
        today = date.today()
        events = []
        for i, (s, e, title, category) in enumerate(_EVENTS):
            first = today + timedelta(days=s)
            last = today + timedelta(days=e) if e is not None else None
            if first <= end and (last or first) >= start:
                events.append(SchoolEvent(f"mock-{i}", title, first, last, category))
        return events
