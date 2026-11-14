import asyncio

from sqlmodel import select

from app.models import (
    ChatMessage, Course, Enrollment, Lesson, LessonStatus, Page, PageLive, Role, User,
)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {
        "status": "ok", "mock_ai": True, "mock_image": True, "ai_provider": "mock", "image_provider": "mock",
    }


def test_cors_allows_localhost(client):
    r = client.options(
        "/health",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_openapi_docs(client):
    assert client.get("/openapi.json").status_code == 200


def test_models_roundtrip(session):
    t = User(login_id="t1", password_hash="x", name="김교사", role=Role.teacher)
    s = User(login_id="s1", password_hash="x", name="이학생", role=Role.student)
    session.add_all([t, s]); session.commit()
    c = Course(teacher_id=t.id, name="과학", invite_code="ABC123")
    session.add(c); session.commit()
    session.add(Enrollment(course_id=c.id, student_id=s.id))
    lesson = Lesson(course_id=c.id, session_no=1, title="광합성")
    session.add(lesson); session.commit()
    session.add(Page(lesson_id=lesson.id, page_no=1, image_path="a.png",
                     easy_sentences=["문장"], hard_words=[{"word": "w", "meaning": "m"}],
                     image_suggestion={"needed": False, "reason": "", "prompt": ""}))
    session.add(PageLive(lesson_id=lesson.id, page_no=1, easy_transcript=["자막"]))
    session.add(ChatMessage(lesson_id=lesson.id, student_id=s.id, role="user", content="질문"))
    session.commit()

    page = session.exec(select(Page)).one()
    assert page.easy_sentences == ["문장"]
    assert page.hard_words[0]["word"] == "w"
    assert lesson.status == LessonStatus.uploaded
    assert session.exec(select(PageLive)).one().easy_transcript == ["자막"]


def test_mock_provider_shapes(tmp_env):
    from app.ai import get_ai_provider

    p = get_ai_provider()
    page = asyncio.run(p.restructure_page("광합성\n식물은..."))
    assert set(page) == {"easy_sentences", "hard_words", "image_suggestion"}
    live = asyncio.run(p.live_caption("src", "오늘은 광합성을 배워요", []))
    assert set(live) == {"easy_transcript", "hard_words"} and live["easy_transcript"]
    quiz = asyncio.run(p.generate_quiz([{"page_no": 1}], []))
    assert all(q["type"] in ("ox", "choice") for q in quiz["questions"])
    pages = [{"page_no": 2, "easy_sentences": ["광합성은 잎에서 일어나요."]}]
    assert asyncio.run(p.chat(pages, [], [], "광합성이 뭐예요?"))["related_page"] == 2
    off = asyncio.run(p.chat(pages, [], [], "축구 좋아해?"))
    assert off["related_page"] is None and off["answer"].startswith("이건 오늘 수업과 다른 이야기예요")
    from app.ai import get_image_provider

    assert asyncio.run(get_image_provider().generate_image("x")).startswith(b"\x89PNG")


def test_captioned_upto_backfilled_on_old_db(tmp_path, monkeypatch):
    """captioned_upto 컬럼이 없던 예전 DB: 추가하면서 기존 페이지는 지금까지의 발화를 처리한 것으로 채운다."""
    import sqlite3

    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE transcript (id INTEGER PRIMARY KEY, lesson_id INTEGER, page_no INTEGER, text TEXT, created_at TEXT);
        CREATE TABLE pagelive (lesson_id INTEGER, page_no INTEGER, easy_transcript JSON, hard_words JSON NOT NULL DEFAULT '[]',
                               updated_at TEXT, PRIMARY KEY (lesson_id, page_no));
        INSERT INTO transcript VALUES (1, 1, 1, 'a', ''), (2, 1, 1, 'b', ''), (3, 1, 2, 'c', '');
        INSERT INTO pagelive VALUES (1, 1, '[]', '[]', ''), (1, 3, '[]', '[]', '');
    """)
    con.commit()
    con.close()
    from sqlalchemy import create_engine

    from app.db import _add_missing_columns

    engine = create_engine(f"sqlite:///{path}")
    _add_missing_columns(engine)
    engine.dispose()
    rows = sqlite3.connect(path).execute("SELECT lesson_id, page_no, captioned_upto FROM pagelive ORDER BY page_no").fetchall()
    assert rows == [(1, 1, 2), (1, 3, 0)]
