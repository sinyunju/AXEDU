"""DB 엔진과 세션 의존성.

라우터는 항상 `Depends(get_session)`으로 세션을 주입받는다.
추후 Postgres로 바꿀 때는 DATABASE_URL만 교체하면 된다.
"""
from collections.abc import Iterator

from sqlalchemy import Engine, inspect, text
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


# create_all은 기존 테이블에 컬럼을 추가하지 않는다. 마이그레이션 도구 대신 해커톤용으로 필요한 컬럼만 추가.
# (table, column, SQL 타입·기본값)
_ADDED_COLUMNS = [
    ("pagelive", "hard_words", "JSON NOT NULL DEFAULT '[]'"),
    ("pagelive", "captioned_upto", "INTEGER NOT NULL DEFAULT 0"),
]

# 컬럼을 새로 추가한 직후 한 번 실행할 값 채우기
_BACKFILL = {
    # 이미 자막이 있는 페이지는 지금까지의 발화를 처리한 것으로 표시 (안 하면 예전 발화를 전부 다시 보냄)
    ("pagelive", "captioned_upto"): (
        "UPDATE pagelive SET captioned_upto = COALESCE((SELECT MAX(t.id) FROM transcript t "
        "WHERE t.lesson_id = pagelive.lesson_id AND t.page_no = pagelive.page_no), 0)"
    ),
}


def _add_missing_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, column, ddl in _ADDED_COLUMNS:
            if not inspector.has_table(table):
                continue
            if column not in {c["name"] for c in inspector.get_columns(table)}:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                if (table, column) in _BACKFILL:
                    conn.execute(text(_BACKFILL[(table, column)]))


def init_db(engine: Engine | None = None) -> None:
    from app import models  # noqa: F401  (테이블 등록)

    engine = engine or get_engine()
    SQLModel.metadata.create_all(engine)
    _add_missing_columns(engine)


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
