"""DB 엔진과 세션 의존성.

라우터는 항상 `Depends(get_session)`으로 세션을 주입받는다.
추후 Postgres로 바꿀 때는 DATABASE_URL만 교체하면 된다.
"""
from collections.abc import Iterator

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_engine: Engine | None = None


def make_engine(url: str) -> Engine:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = make_engine(get_settings().database_url)
    return _engine


def init_db(engine: Engine | None = None) -> None:
    from app import models  # noqa: F401  (테이블 등록)

    SQLModel.metadata.create_all(engine or get_engine())


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
