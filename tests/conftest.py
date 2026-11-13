import os

# 테스트는 항상 MOCK_AI + 임시 DB로 실행 (app import 전에 설정)
os.environ["MOCK_AI"] = "true"
os.environ["JWT_SECRET"] = "test-secret-at-least-32-bytes-long-xxxxxxxx"

import bcrypt
import pytest

# 테스트 속도용: bcrypt cost를 최소(4)로. 운영 코드(app/security.py)는 기본값(12) 그대로.
_orig_gensalt = bcrypt.gensalt
bcrypt.gensalt = lambda rounds=4, prefix=b"2b": _orig_gensalt(4, prefix)
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel


@pytest.fixture()
def tmp_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    from app import db
    from app.ai import get_ai_provider
    from app.config import get_settings

    get_settings.cache_clear()
    get_ai_provider.cache_clear()
    db._engine = None
    yield
    if db._engine is not None:
        db._engine.dispose()
    db._engine = None
    get_settings.cache_clear()
    get_ai_provider.cache_clear()


@pytest.fixture()
def client(tmp_env):
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture()
def session(tmp_env):
    from app.db import get_engine, init_db

    init_db()
    with Session(get_engine()) as s:
        yield s
