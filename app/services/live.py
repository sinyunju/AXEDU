"""실시간 수업: WebSocket 연결 관리 + 실시간 쉬운 자막 (SPEC.md 5·6절).

⚠️ 단일 프로세스 전제
연결 목록(ConnectionManager)과 페이지별 자막 상태(LiveCaptioner)를 이 프로세스 메모리에 둔다.
uvicorn --workers 2 이상이나 서버 여러 대로 띄우면 교사와 학생이 서로 다른 프로세스에 붙어
메시지가 전달되지 않고, 15초 간격·페이지별 lock도 프로세스마다 따로 동작한다.
여러 프로세스로 늘리려면 Redis pub/sub 같은 외부 브로커와 분산 lock으로 바꿔야 한다.
"""
import asyncio
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket
from sqlmodel import Session, select

from app.ai import AIProvider, get_ai_provider
from app.db import get_engine
from app.models import Page, PageLive, Role, Transcript, utcnow

logger = logging.getLogger(__name__)

# LLM에 한 번에 넘기는 새 발화 최대 길이 (넘으면 나눠서 처리)
MAX_TRANSCRIPT_CHARS = 4000
# 문맥용으로 함께 넘기는 직전 발화(이미 자막으로 만든 부분) 길이
CONTEXT_CHARS = 400

CAPTION_TYPES = ("content", "flow", "notice")


def normalize_captions(items: list[Any] | None) -> list[dict[str, str]]:
    """자막 항목을 [{text, type}]로 통일.

    - 예전 형식(문자열 목록)으로 저장된 자막은 type=content로 읽는다.
    - 알 수 없는 type은 content, 빈 문장은 버린다.
    """
    out: list[dict[str, str]] = []
    for item in items or []:
        if isinstance(item, str):
            text, kind = item, "content"
        elif isinstance(item, dict):
            text, kind = str(item.get("text", "")), str(item.get("type", "content"))
        else:
            continue
        text = text.strip()
        if text:
            out.append({"text": text, "type": kind if kind in CAPTION_TYPES else "content"})
    return out


class ConnectionManager:
    """lesson_id별 WebSocket 연결 목록 (in-memory)."""

    def __init__(self) -> None:
        self._rooms: dict[int, dict[WebSocket, Role]] = defaultdict(dict)

    def add(self, lesson_id: int, ws: WebSocket, role: Role) -> None:
        self._rooms[lesson_id][ws] = role

    def remove(self, lesson_id: int, ws: WebSocket) -> None:
        room = self._rooms.get(lesson_id)
        if room is not None:
            room.pop(ws, None)
            if not room:
                del self._rooms[lesson_id]

    def count(self, lesson_id: int, role: Role | None = None) -> int:
        room = self._rooms.get(lesson_id, {})
        return sum(1 for r in room.values() if role is None or r == role)

    async def broadcast(self, lesson_id: int, message: dict[str, Any], *, role: Role | None = None) -> None:
        """교사·학생 모두(role을 주면 그 역할만)에게 전송. 보내기 실패한 연결은 정리한다."""
        for ws, r in list(self._rooms.get(lesson_id, {}).items()):
            if role is not None and r != role:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                self.remove(lesson_id, ws)


@dataclass
class _PageState:
    pending: bool = False  # 마지막 LLM 호출 이후 새 발화가 있음
    last_call: float | None = None  # 마지막 LLM 호출 시각 (monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)  # 같은 페이지 호출이 겹치지 않도록


class LiveCaptioner:
    """페이지별 발화를 모아 조건이 맞으면 LLM으로 쉬운 자막을 만들어 broadcast.

    호출 조건 (6절):
      (a) 마지막 호출 후 interval초 경과 + 새 텍스트 있음  → on_transcript() 또는 tick()
      (b) page_change로 이전 페이지 확정                    → flush()
    페이지의 첫 발화는 기다리지 않고 바로 호출한다 (마지막 호출이 없으므로 경과로 간주).
    """

    def __init__(self, manager: ConnectionManager, interval: float,
                 provider_getter: Callable[[], AIProvider] = get_ai_provider,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.manager = manager
        self.interval = interval
        self._provider_getter = provider_getter
        self._clock = clock
        self._states: dict[tuple[int, int], _PageState] = {}
        self._tasks: set[asyncio.Task] = set()

    def _state(self, lesson_id: int, page_no: int) -> _PageState:
        return self._states.setdefault((lesson_id, page_no), _PageState())

    def _due(self, st: _PageState) -> bool:
        return st.last_call is None or self._clock() - st.last_call >= self.interval

    def on_transcript(self, lesson_id: int, page_no: int) -> None:
        st = self._state(lesson_id, page_no)
        st.pending = True
        if self._due(st):
            self._schedule(lesson_id, page_no, force=False)

    def flush(self, lesson_id: int, page_no: int) -> None:
        """간격과 관계없이 남은 발화를 바로 처리 (페이지 이동·수업 종료)."""
        st = self._states.get((lesson_id, page_no))
        if st is not None and st.pending:
            self._schedule(lesson_id, page_no, force=True)

    def flush_lesson(self, lesson_id: int) -> None:
        for lid, page_no in list(self._states):
            if lid == lesson_id:
                self.flush(lid, page_no)

    def tick(self) -> None:
        """주기적으로 호출: 간격이 지났는데 처리 안 된 발화가 있으면 호출 예약."""
        for (lesson_id, page_no), st in list(self._states.items()):
            if st.pending and not st.lock.locked() and self._due(st):
                self._schedule(lesson_id, page_no, force=False)

    async def run_ticker(self, period: float = 1.0) -> None:
        while True:
            await asyncio.sleep(period)
            try:
                self.tick()
            except Exception:
                logger.exception("자막 ticker 오류")

    async def wait_idle(self) -> None:
        """예약된 자막 작업이 모두 끝날 때까지 대기 (테스트·종료용)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    def _schedule(self, lesson_id: int, page_no: int, *, force: bool) -> None:
        task = asyncio.create_task(self._run(lesson_id, page_no, force=force))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, lesson_id: int, page_no: int, *, force: bool) -> None:
        st = self._state(lesson_id, page_no)
        async with st.lock:
            # lock을 기다리는 동안 앞선 호출이 이미 처리했거나, 간격이 아직 안 됐으면 건너뜀
            if not st.pending or (not force and not self._due(st)):
                return
            st.pending = False
            st.last_call = self._clock()
            try:
                result = await self._caption(lesson_id, page_no)
            except Exception:
                logger.exception("실시간 자막 실패 lesson=%s page=%s (다음 주기에 재시도)", lesson_id, page_no)
                st.pending = True
                return
            if result is not None:
                await self.manager.broadcast(lesson_id, {"type": "page_update", "page_no": page_no, **result})

    async def _caption(self, lesson_id: int, page_no: int) -> dict[str, Any] | None:
        """아직 자막으로 만들지 않은 발화만 LLM에 넘기고, 돌아온 새 자막을 이전 자막 뒤에 붙인다.

        LLM이 자막 전체를 다시 쓰게 하면 이전 자막을 되풀이하거나 새 말을 빠뜨리기 쉬워서
        (빠른 모델에서 특히), 서버가 "어디까지 처리했는지"를 기억하고 이어 붙이는 방식으로 한다.
        """
        with Session(get_engine()) as session:
            page = session.exec(select(Page).where(Page.lesson_id == lesson_id, Page.page_no == page_no)).first()
            if page is None:
                return None
            live = session.get(PageLive, (lesson_id, page_no))
            upto = live.captioned_upto if live else 0
            rows = session.exec(
                select(Transcript.id, Transcript.text)
                .where(Transcript.lesson_id == lesson_id, Transcript.page_no == page_no)
                .order_by(Transcript.id)
            ).all()
            source_text = page.source_text
            previous = normalize_captions(live.easy_transcript) if live else []
            previous_words = list(live.hard_words) if live else []

        done = [text for tid, text in rows if tid <= upto]
        new_rows: list[tuple[int, str]] = []
        size = 0
        for tid, text in rows:
            if tid <= upto:
                continue
            if new_rows and size + len(text) > MAX_TRANSCRIPT_CHARS:
                break  # 너무 많이 밀렸으면 나눠서 처리 (남은 것은 다음 주기에)
            new_rows.append((tid, text))
            size += len(text)
        if not new_rows:
            return None
        if len(new_rows) < sum(1 for tid, _ in rows if tid > upto):
            self._state(lesson_id, page_no).pending = True

        transcript = " ".join(text for _, text in new_rows)
        context = " ".join(done)[-CONTEXT_CHARS:]
        out = await self._provider_getter().live_caption(source_text, transcript, previous, context)
        added = _new_captions(previous, normalize_captions(out.get("easy_transcript")))
        easy = previous + added
        words = _merge_hard_words(previous_words, out.get("hard_words", []))
        changed = bool(added) or words != previous_words

        with Session(get_engine()) as session:
            live = session.get(PageLive, (lesson_id, page_no)) or PageLive(lesson_id=lesson_id, page_no=page_no)
            live.captioned_upto = new_rows[-1][0]  # 잡담뿐이었어도 처리한 것으로 기록 (다시 보내지 않음)
            if changed:
                live.easy_transcript = easy
                live.hard_words = words
                live.updated_at = utcnow()
            session.add(live)
            session.commit()
        if not changed:
            return None  # 잡담·반복만 있었던 경우: 전송하지 않음
        return {"easy_transcript": easy, "hard_words": words}


def _norm(text: str) -> str:
    """중복 비교용: 공백·문장부호를 빼고 비교."""
    return "".join(ch for ch in text if ch.isalnum())


def _new_captions(previous: list[dict[str, str]], new: list[dict[str, str]]) -> list[dict[str, str]]:
    """이미 나간 자막과 같은 문장, 새 자막 안에서 되풀이된 문장을 뺀다 (LLM이 지시를 어겨도 중복이 안 나가게)."""
    seen = {_norm(c["text"]) for c in previous}
    out = []
    for c in new:
        key = _norm(c["text"])
        if key and key not in seen:
            seen.add(key)
            out.append(c)
    return out


def _merge_hard_words(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """같은 낱말은 하나만 (먼저 나온 뜻 유지). 자막이 쌓여도 이미 나온 낱말이 사라지지 않게."""
    merged: dict[str, dict[str, Any]] = {}
    for w in [*old, *new]:
        word = str(w.get("word", "")).strip()
        if word and word not in merged:
            merged[word] = {"word": word, "meaning": str(w.get("meaning", "")).strip()}
    return list(merged.values())


class LiveHub:
    """앱 하나당 하나. app.state.live 에 둔다."""

    def __init__(self, interval: float, provider_getter: Callable[[], AIProvider] = get_ai_provider) -> None:
        self.connections = ConnectionManager()
        self.captioner = LiveCaptioner(self.connections, interval, provider_getter)
