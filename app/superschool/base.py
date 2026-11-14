from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime

from app.models import Role


class SuperschoolError(RuntimeError):
    """슈퍼스쿨 호출 실패 (잘못된·만료된 code, 네트워크, 응답 형식 오류)."""


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True)
class SuperschoolProfile:
    superschool_id: str  # 슈퍼스쿨 안에서 사용자를 구분하는 값 (계정 연결의 기준)
    name: str
    role: Role
    school: str  # 화면에 보일 소속. 예) "천천중학교 2학년 3반", "천천중학교 · 과학과"


@dataclass(frozen=True)
class SchoolEvent:
    id: str
    title: str
    start: date
    end: date | None  # 여러 날 일정의 마지막 날 (포함)
    category: str  # 시험 | 행사 | 휴업일 ...


class SuperschoolClient(ABC):
    name = "base"

    @abstractmethod
    def authorize_url(self, *, redirect_uri: str, state: str, mode: str, role: Role | None) -> str:
        """사용자를 보낼 슈퍼스쿨 로그인·동의 화면 주소."""

    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str, *, role_hint: Role | None = None) -> Tokens:
        """인가 code → 토큰. role_hint는 목 모드에서 '이 계정 연결'용 가짜 계정을 고를 때만 쓴다."""

    @abstractmethod
    async def refresh(self, refresh_token: str) -> Tokens:
        """만료된 access_token 갱신."""

    @abstractmethod
    async def get_profile(self, access_token: str) -> SuperschoolProfile:
        """이름·역할·소속."""

    @abstractmethod
    async def get_events(self, access_token: str, start: date, end: date) -> list[SchoolEvent]:
        """학사 일정 (start~end, 양 끝 포함)."""
