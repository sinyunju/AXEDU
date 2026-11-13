import asyncio

import pytest
from sqlmodel import Session, select
from starlette.websockets import WebSocketDisconnect

from app.ai.mock import MockProvider
from app.models import Lesson, LessonStatus, Page, PageLive, Transcript
from app.services.live import LiveCaptioner, _merge_hard_words
from tests.helpers import make_pdf, make_user

PDF = make_pdf(["광합성이란? 식물이 빛으로 양분을 만드는 과정", "엽록체의 구조", "정리"])


class CountingProvider(MockProvider):
    def __init__(self):
        self.calls: list[tuple[str, list[str]]] = []

    async def live_caption(self, source_text, transcript, previous_easy):
        self.calls.append((transcript, list(previous_easy)))
        out = await super().live_caption(source_text, transcript, previous_easy)
        return {**out, "hard_words": [{"word": f"낱말{len(self.calls)}", "meaning": "뜻"}]}


@pytest.fixture()
def ctx(client):
    t1 = make_user(client, "tch1", "teacher")
    t2 = make_user(client, "tch2", "teacher")
    s1 = make_user(client, "stu1", "student")
    s2 = make_user(client, "stu2", "student")
    course = client.post("/courses", json={"name": "과학"}, headers=t1["headers"]).json()
    client.post("/courses/join", json={"invite_code": course["invite_code"]}, headers=s1["headers"])
    lesson_id = client.post(f"/courses/{course['id']}/lessons", data={"session_no": "1", "title": "광합성"},
                            files={"file": ("a.pdf", PDF, "application/pdf")}, headers=t1["headers"]).json()["id"]
    tokens = {k: v["headers"]["Authorization"].split()[1] for k, v in
              {"t1": t1, "t2": t2, "s1": s1, "s2": s2}.items()}
    provider = CountingProvider()
    client.app.state.live.captioner._provider_getter = lambda: provider
    return {"t1": t1, "s1": s1, "lesson_id": lesson_id, "tokens": tokens, "provider": provider}


def ready_and_start(client, ctx, start=True):
    h = ctx["t1"]["headers"]
    client.post(f"/lessons/{ctx['lesson_id']}/generate", headers=h)
    client.post(f"/lessons/{ctx['lesson_id']}/approve", headers=h)
    if start:
        assert client.post(f"/lessons/{ctx['lesson_id']}/start", headers=h).json()["status"] == "live"


def ws_url(ctx, who=None, lesson_id=None):
    token = ctx["tokens"][who] if who else ""
    return f"/ws/lessons/{lesson_id or ctx['lesson_id']}?token={token}"


def recv_until(ws, type_):
    """type_ 메시지가 올 때까지 받기. (메시지 순서는 task 스케줄링에 따라 달라질 수 있음)"""
    others = []
    while True:
        msg = ws.receive_json()
        if msg["type"] == type_:
            return msg, others
        others.append(msg)


def wait_idle(client):
    client.portal.call(client.app.state.live.captioner.wait_idle)


def close_code(client, url):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(url) as ws:
            ws.receive_json()
    return e.value.code


# ---------- 연결 인증 ----------
def test_connection_rejected(client, ctx):
    assert close_code(client, ws_url(ctx)) == 4401  # 토큰 없음
    assert close_code(client, f"/ws/lessons/{ctx['lesson_id']}?token=garbage") == 4401
    assert close_code(client, ws_url(ctx, "t2")) == 4403  # 다른 교사
    assert close_code(client, ws_url(ctx, "s2")) == 4403  # 미등록 학생
    assert close_code(client, ws_url(ctx, "s1")) == 4404  # 미승인 회차
    assert close_code(client, ws_url(ctx, "t1", lesson_id=9999)) == 4404


def test_connect_sends_current_state(client, ctx):
    ready_and_start(client, ctx)
    with client.websocket_connect(ws_url(ctx, "s1")) as ws:
        assert ws.receive_json() == {"type": "teacher_page", "page_no": 1}
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


# ---------- 실시간 흐름 ----------
def test_transcript_page_change_flow(client, session, ctx):
    ready_and_start(client, ctx)
    provider = ctx["provider"]
    with client.websocket_connect(ws_url(ctx, "t1")) as teacher, client.websocket_connect(ws_url(ctx, "s1")) as student:
        teacher.receive_json(), student.receive_json()  # 초기 teacher_page

        # 페이지 첫 발화 → 바로 LLM 호출 → 학생에게 page_update
        teacher.send_json({"type": "transcript", "page_no": 1, "text": "오늘은 광합성을 배워요", "final": True})
        ack, _ = recv_until(teacher, "ack")
        assert ack["for"] == "transcript" and ack["transcript_id"]
        first, _ = recv_until(student, "page_update")
        assert first["page_no"] == 1 and first["easy_transcript"]
        assert first["hard_words"] == [{"word": "낱말1", "meaning": "뜻"}]
        recv_until(teacher, "page_update")  # 교사 화면도 같은 자막을 받음

        # 15초 안의 추가 발화 → 저장만 하고 LLM은 호출하지 않음 (a)
        teacher.send_json({"type": "transcript", "page_no": 1, "text": "식물은 햇빛이 필요해요", "final": True})
        recv_until(teacher, "ack")
        wait_idle(client)
        assert len(provider.calls) == 1

        # 페이지 이동 → teacher_page broadcast + 이전 페이지 확정 호출 (b)
        teacher.send_json({"type": "page_change", "page_no": 2})
        tp, _ = recv_until(student, "teacher_page")
        assert tp == {"type": "teacher_page", "page_no": 2}
        update, _ = recv_until(student, "page_update")
        assert update["page_no"] == 1
        assert {w["word"] for w in update["hard_words"]} == {"낱말1", "낱말2"}  # 앞서 나온 낱말 유지
        wait_idle(client)
        assert len(provider.calls) == 2
        transcript, previous = provider.calls[1]
        assert transcript == "오늘은 광합성을 배워요 식물은 햇빛이 필요해요"  # 누적 발화 전체
        assert previous == first["easy_transcript"]  # 직전 자막을 LLM에 함께 넘김

    assert session.exec(select(Lesson)).one().current_page == 2
    assert len(session.exec(select(Transcript)).all()) == 2
    live = session.get(PageLive, (ctx["lesson_id"], 1))
    assert live.easy_transcript == update["easy_transcript"] and len(live.hard_words) == 2


def test_reconnect_restores_state(client, ctx):
    ready_and_start(client, ctx)
    with client.websocket_connect(ws_url(ctx, "t1")) as teacher:
        teacher.receive_json()
        teacher.send_json({"type": "transcript", "page_no": 1, "text": "광합성은 잎에서 일어나요"})
        recv_until(teacher, "page_update")

    # 학생이 나중에(또는 다시) 접속하면 현재 페이지와 그 페이지 자막을 바로 받음
    with client.websocket_connect(ws_url(ctx, "s1")) as student:
        assert student.receive_json() == {"type": "teacher_page", "page_no": 1}
        restored = student.receive_json()
        assert restored["type"] == "page_update" and restored["easy_transcript"]

    # REST 페이지 조회에도 실시간 낱말이 포함됨
    v = client.get(f"/lessons/{ctx['lesson_id']}/pages/1", headers=ctx["s1"]["headers"]).json()
    assert v["easy_transcript"] == restored["easy_transcript"]
    assert v["transcript_hard_words"] == restored["hard_words"]


def test_start_and_end_are_broadcast(client, ctx):
    ready_and_start(client, ctx, start=False)
    h = ctx["t1"]["headers"]
    with client.websocket_connect(ws_url(ctx, "s1")) as student:  # 시작 전(approved)에도 접속 가능
        assert student.receive_json() == {"type": "teacher_page", "page_no": 1}
        client.post(f"/lessons/{ctx['lesson_id']}/start", headers=h)
        assert student.receive_json() == {"type": "lesson_started", "page_no": 1}
        client.post(f"/lessons/{ctx['lesson_id']}/end", headers=h)
        assert student.receive_json() == {"type": "lesson_ended"}

    with client.websocket_connect(ws_url(ctx, "s1")) as student:  # 종료 후 접속 시 종료 상태 복원
        assert student.receive_json()["type"] == "teacher_page"
        assert student.receive_json() == {"type": "lesson_ended"}


def test_end_flushes_pending_transcript(client, ctx):
    ready_and_start(client, ctx)
    with client.websocket_connect(ws_url(ctx, "t1")) as teacher, client.websocket_connect(ws_url(ctx, "s1")) as student:
        teacher.receive_json(), student.receive_json()
        teacher.send_json({"type": "transcript", "page_no": 1, "text": "첫 문장"})
        recv_until(student, "page_update")
        teacher.send_json({"type": "transcript", "page_no": 1, "text": "마지막 문장"})  # 간격 안이라 대기
        recv_until(teacher, "ack")
        client.post(f"/lessons/{ctx['lesson_id']}/end", headers=ctx["t1"]["headers"])
        recv_until(student, "lesson_ended")
        update, _ = recv_until(student, "page_update")  # 종료 시 남은 발화도 처리
        assert "마지막 문장" in ctx["provider"].calls[-1][0]


# ---------- 잘못된 메시지 ----------
def test_teacher_message_errors(client, session, ctx):
    ready_and_start(client, ctx, start=False)
    with client.websocket_connect(ws_url(ctx, "t1")) as teacher:
        teacher.receive_json()

        def send(msg):
            teacher.send_json(msg) if isinstance(msg, dict) else teacher.send_text(msg)
            return teacher.receive_json()

        assert send({"type": "transcript", "page_no": 1, "text": "x"})["type"] == "error"  # 수업 시작 전
        client.post(f"/lessons/{ctx['lesson_id']}/start", headers=ctx["t1"]["headers"])
        assert teacher.receive_json()["type"] == "lesson_started"  # 교사 연결에도 broadcast
        assert send("not json")["type"] == "error"
        assert send({"type": "unknown"})["type"] == "error"
        assert send({"type": "page_change", "page_no": 99})["type"] == "error"
        assert send({"type": "page_change"})["type"] == "error"
        assert send({"type": "transcript", "page_no": 1, "text": "   "})["type"] == "error"
        assert send({"type": "transcript", "page_no": 1, "text": "x" * 2001})["type"] == "error"
        r = send({"type": "transcript", "page_no": 1, "text": "중간 결과", "final": False})
        assert r["type"] == "ack" and r["ignored"] is True
        assert send({"type": "ping"}) == {"type": "pong"}
    assert session.exec(select(Transcript)).all() == []  # 하나도 저장되지 않음


def test_student_cannot_send_teacher_messages(client, ctx):
    ready_and_start(client, ctx)
    with client.websocket_connect(ws_url(ctx, "s1")) as student:
        student.receive_json()
        for msg in ({"type": "page_change", "page_no": 2}, {"type": "transcript", "page_no": 1, "text": "x"}):
            student.send_json(msg)
            assert student.receive_json()["type"] == "error"


# ---------- LiveCaptioner 단위 테스트 (가짜 시계) ----------
class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FakeManager:
    def __init__(self):
        self.sent: list[dict] = []

    async def broadcast(self, lesson_id, message):
        self.sent.append(message)


@pytest.fixture()
def lesson_with_page(session):
    lesson = Lesson(course_id=1, session_no=1, title="t", status=LessonStatus.live)
    session.add(lesson)
    session.commit()
    session.add(Page(lesson_id=lesson.id, page_no=1, image_path="x.png", source_text="광합성"))
    session.commit()
    return lesson.id


def add_transcript(session, lesson_id, text):
    session.add(Transcript(lesson_id=lesson_id, page_no=1, text=text))
    session.commit()


def test_interval_and_ticker(session, lesson_with_page):
    lid = lesson_with_page
    clock, manager, provider = FakeClock(), FakeManager(), CountingProvider()
    cap = LiveCaptioner(manager, interval=15, provider_getter=lambda: provider, clock=clock)

    async def scenario():
        add_transcript(session, lid, "하나")
        cap.on_transcript(lid, 1)  # 첫 발화: 바로 호출
        await cap.wait_idle()
        assert len(provider.calls) == 1

        clock.now += 10
        add_transcript(session, lid, "둘")
        cap.on_transcript(lid, 1)
        cap.tick()
        await cap.wait_idle()
        assert len(provider.calls) == 1  # 10초: 아직

        clock.now += 5  # 마지막 호출 후 15초
        cap.tick()
        await cap.wait_idle()
        assert len(provider.calls) == 2 and provider.calls[1][0] == "하나 둘"

        clock.now += 100
        cap.tick()  # 새 텍스트가 없으면 호출 안 함
        await cap.wait_idle()
        assert len(provider.calls) == 2

    asyncio.run(scenario())
    assert [m["type"] for m in manager.sent] == ["page_update", "page_update"]


def test_page_lock_prevents_overlap(session, lesson_with_page):
    lid = lesson_with_page
    running, max_running = 0, 0

    class Slow(CountingProvider):
        async def live_caption(self, *a):
            nonlocal running, max_running
            running += 1
            max_running = max(max_running, running)
            await asyncio.sleep(0.05)
            running -= 1
            return await super().live_caption(*a)

    provider = Slow()
    cap = LiveCaptioner(FakeManager(), interval=0, provider_getter=lambda: provider, clock=FakeClock())

    async def scenario():
        add_transcript(session, lid, "하나")
        cap.on_transcript(lid, 1)
        await asyncio.sleep(0.01)  # 첫 호출 진행 중에
        add_transcript(session, lid, "둘")
        cap.on_transcript(lid, 1)
        cap.flush(lid, 1)
        cap.tick()
        await cap.wait_idle()

    asyncio.run(scenario())
    assert max_running == 1  # 같은 페이지 호출은 겹치지 않음
    assert len(provider.calls) == 2  # 진행 중에 들어온 발화는 한 번 더 처리 (중복 호출 없이)
    assert provider.calls[1][0] == "하나 둘"


def test_failure_is_retried_later(session, lesson_with_page):
    lid = lesson_with_page
    clock, manager = FakeClock(), FakeManager()
    attempts = []

    class Flaky(MockProvider):
        async def live_caption(self, *a):
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("gateway down")
            return await super().live_caption(*a)

    cap = LiveCaptioner(manager, interval=15, provider_getter=lambda: Flaky(), clock=clock)

    async def scenario():
        add_transcript(session, lid, "하나")
        cap.on_transcript(lid, 1)
        await cap.wait_idle()
        assert manager.sent == []  # 실패: 보내지 않음
        clock.now += 15
        cap.tick()
        await cap.wait_idle()

    asyncio.run(scenario())
    assert len(attempts) == 2 and manager.sent[0]["type"] == "page_update"


def test_merge_hard_words():
    old = [{"word": "광합성", "meaning": "a"}]
    new = [{"word": "광합성", "meaning": "b"}, {"word": " 엽록체 ", "meaning": "c"}, {"word": "", "meaning": "x"}]
    assert _merge_hard_words(old, new) == [{"word": "광합성", "meaning": "a"}, {"word": "엽록체", "meaning": "c"}]


def test_init_db_adds_missing_column(tmp_path):
    from sqlalchemy import inspect, text

    from app.db import init_db, make_engine

    engine = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:  # 7단계 이전 구조의 pagelive
        conn.execute(text("CREATE TABLE pagelive (lesson_id INTEGER, page_no INTEGER, easy_transcript JSON, "
                          "updated_at DATETIME, PRIMARY KEY (lesson_id, page_no))"))
        conn.execute(text("INSERT INTO pagelive VALUES (1, 1, '[\"a\"]', '2026-01-01')"))
    init_db(engine)
    assert "hard_words" in {c["name"] for c in inspect(engine).get_columns("pagelive")}
    with Session(engine) as s:
        live = s.get(PageLive, (1, 1))
        assert live.easy_transcript == ["a"] and live.hard_words == []
    engine.dispose()
