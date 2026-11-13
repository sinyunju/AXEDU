"""WebSocket: /ws/lessons/{lesson_id}?token=<JWT>  (CLAUDE.md 5절)

연결 관리와 자막 상태는 in-memory (단일 프로세스 전제, app/services/live.py 참고).

연결 거부 시 accept 후 아래 코드로 close 한다 (브라우저에서 CloseEvent.code로 확인 가능):
  4401 토큰 없음/무효, 4403 권한 없음, 4404 회차 없음(학생에게는 미승인 회차 포함)
"""
import json
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from sqlmodel import Session, func, select

from app.db import get_engine
from app.models import Course, Lesson, LessonStatus, Page, PageLive, Role, Transcript, User
from app.permissions import STUDENT_VISIBLE_STATUSES, is_enrolled
from app.security import decode_access_token
from app.services.live import LiveHub, normalize_captions

logger = logging.getLogger(__name__)
router = APIRouter()

CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_NOT_FOUND = 4404

MAX_TRANSCRIPT_TEXT = 2000


class PingMsg(BaseModel):
    type: Literal["ping"]


class PageChangeMsg(BaseModel):
    type: Literal["page_change"]
    page_no: int


class TranscriptMsg(BaseModel):
    type: Literal["transcript"]
    page_no: int
    text: str = Field(max_length=MAX_TRANSCRIPT_TEXT)
    final: bool = True


_Incoming = TypeAdapter(Annotated[PingMsg | PageChangeMsg | TranscriptMsg, Field(discriminator="type")])


class _Reject(Exception):
    def __init__(self, code: int, reason: str):
        self.code, self.reason = code, reason


def _authorize(lesson_id: int, token: str) -> tuple[User, Lesson]:
    with Session(get_engine()) as session:
        user_id = decode_access_token(token) if token else None
        user = session.get(User, user_id) if user_id is not None else None
        if user is None:
            raise _Reject(CLOSE_UNAUTHORIZED, "로그인이 필요합니다")
        lesson = session.get(Lesson, lesson_id)
        if lesson is None:
            raise _Reject(CLOSE_NOT_FOUND, "수업 회차를 찾을 수 없습니다")
        if user.role == Role.teacher:
            course = session.get(Course, lesson.course_id)
            if course is None or course.teacher_id != user.id:
                raise _Reject(CLOSE_FORBIDDEN, "내 과목이 아닙니다")
        else:
            if not is_enrolled(session, lesson.course_id, user.id):
                raise _Reject(CLOSE_FORBIDDEN, "등록하지 않은 과목입니다")
            if lesson.status not in STUDENT_VISIBLE_STATUSES:
                raise _Reject(CLOSE_NOT_FOUND, "수업 회차를 찾을 수 없습니다")
        session.expunge(user)
        session.expunge(lesson)
        return user, lesson


def _snapshot(lesson_id: int) -> tuple[Lesson, int, PageLive | None]:
    with Session(get_engine()) as session:
        lesson = session.get(Lesson, lesson_id)
        page_count = session.exec(select(func.count()).select_from(Page).where(Page.lesson_id == lesson_id)).one()
        live = session.get(PageLive, (lesson_id, lesson.current_page))
        session.expunge(lesson)
        if live is not None:
            session.expunge(live)
        return lesson, page_count, live


@router.websocket("/ws/lessons/{lesson_id}")
async def lesson_socket(websocket: WebSocket, lesson_id: int, token: str = Query("")) -> None:
    await websocket.accept()
    try:
        user, _ = _authorize(lesson_id, token)
    except _Reject as r:
        await websocket.close(code=r.code, reason=r.reason)
        return

    hub: LiveHub = websocket.app.state.live
    hub.connections.add(lesson_id, websocket, user.role)
    try:
        # 연결(재연결) 즉시 현재 상태 복원
        lesson, _, live = _snapshot(lesson_id)
        await websocket.send_json({"type": "teacher_page", "page_no": lesson.current_page})
        if live is not None:
            await websocket.send_json({"type": "page_update", "page_no": live.page_no,
                                       "easy_transcript": normalize_captions(live.easy_transcript),
                                       "hard_words": live.hard_words})
        if lesson.status == LessonStatus.ended:
            await websocket.send_json({"type": "lesson_ended"})

        while True:
            raw = await websocket.receive_text()
            reply = await _handle(hub, lesson_id, user, raw)
            if reply is not None:
                await websocket.send_json(reply)
    except WebSocketDisconnect:
        pass
    finally:
        hub.connections.remove(lesson_id, websocket)


def _error(detail: str) -> dict:
    return {"type": "error", "detail": detail}


async def _handle(hub: LiveHub, lesson_id: int, user: User, raw: str) -> dict | None:
    try:
        msg = _Incoming.validate_python(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as e:
        return _error(f"메시지 형식이 올바르지 않습니다: {e.__class__.__name__}")

    if isinstance(msg, PingMsg):
        return {"type": "pong"}
    if user.role != Role.teacher:
        return _error("학생은 ping만 보낼 수 있습니다")

    with Session(get_engine()) as session:
        lesson = session.get(Lesson, lesson_id)
        if lesson is None:
            return _error("수업 회차를 찾을 수 없습니다")
        if lesson.status != LessonStatus.live:
            return _error("수업이 진행 중이 아닙니다. POST /lessons/{id}/start 로 시작하세요")
        page_count = session.exec(select(func.count()).select_from(Page).where(Page.lesson_id == lesson_id)).one()
        if not 1 <= msg.page_no <= page_count:
            return _error(f"page_no는 1~{page_count} 사이여야 합니다")

        if isinstance(msg, PageChangeMsg):
            previous = lesson.current_page
            lesson.current_page = msg.page_no
            session.add(lesson)
            session.commit()
            await hub.connections.broadcast(lesson_id, {"type": "teacher_page", "page_no": msg.page_no})
            if previous != msg.page_no:
                hub.captioner.flush(lesson_id, previous)  # (b) 이전 페이지 확정
            return {"type": "ack", "for": "page_change", "page_no": msg.page_no}

        # transcript
        if not msg.final:
            return {"type": "ack", "for": "transcript", "page_no": msg.page_no, "ignored": True}
        text = msg.text.strip()
        if not text:
            return _error("text가 비어 있습니다")
        transcript = Transcript(lesson_id=lesson_id, page_no=msg.page_no, text=text)
        session.add(transcript)
        session.commit()
        transcript_id = transcript.id
    hub.captioner.on_transcript(lesson_id, msg.page_no)
    return {"type": "ack", "for": "transcript", "page_no": msg.page_no, "transcript_id": transcript_id}
