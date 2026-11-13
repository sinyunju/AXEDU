"""데모용 리플레이: 미리 준비한 (시각, 페이지 번호, 발화 텍스트) JSON을 교사 WebSocket 클라이언트처럼 재생한다.

  .venv/bin/python -m scripts.replay samples/replay_photosynthesis.json --lesson 2 --start --end
  .venv/bin/python -m scripts.replay samples/replay_photosynthesis.json --lesson 2 --speed 3   # 3배속

옵션
  --lesson N      회차 id (필수)
  --teacher ID    교사 아이디 (기본 teacher1, 비밀번호 --password, 기본 pass1234)
  --server URL    기본 http://localhost:8000
  --speed X       재생 배속 (기본 1.0)
  --start         재생 전에 POST /lessons/{id}/start (승인된 회차여야 함)
  --end           재생 후 POST /lessons/{id}/end (남은 발화가 마지막으로 자막 처리됨)
  --tail SEC      마지막 발화 후 자막을 기다리는 시간 (기본 5초)

JSON 형식 (events만 있는 배열도 허용)
  {
    "title": "설명 (선택)",
    "events": [
      {"t": 0,    "page_no": 1, "text": "자 오늘은 광합성을 배워 볼 거예요"},
      {"t": 6.5,  "page_no": 1, "text": "식물은 햇빛으로 양분을 만들어요"},
      {"t": 30,   "page_no": 2},                       ← 발화 없이 페이지 이동만
      {"t": 31,   "page_no": 2, "text": "여기 초록색 알갱이 보이죠"}
    ]
  }
  - t: 재생 시작부터의 초. 정렬되어 있지 않아도 됨 (같은 t는 파일 순서 유지)
  - page_no가 이전과 다르면 발화 전에 page_change를 자동으로 보낸다
"""
import argparse
import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Event:
    t: float
    page_no: int
    text: str | None = None


def load_events(data: Any) -> list[Event]:
    """JSON 데이터(dict 또는 list) → 시간순 Event 목록. 형식이 틀리면 ValueError."""
    raw = data.get("events") if isinstance(data, dict) else data
    if not isinstance(raw, list) or not raw:
        raise ValueError("events 배열이 비어 있거나 없습니다")
    events = []
    for i, e in enumerate(raw):
        if not isinstance(e, dict):
            raise ValueError(f"events[{i}]가 객체가 아닙니다")
        t, page_no, text = e.get("t"), e.get("page_no"), e.get("text")
        if isinstance(t, bool) or not isinstance(t, int | float) or t < 0:
            raise ValueError(f"events[{i}].t는 0 이상의 숫자여야 합니다: {t!r}")
        if isinstance(page_no, bool) or not isinstance(page_no, int) or page_no < 1:
            raise ValueError(f"events[{i}].page_no는 1 이상의 정수여야 합니다: {page_no!r}")
        if text is not None and not isinstance(text, str):
            raise ValueError(f"events[{i}].text는 문자열이어야 합니다")
        events.append(Event(float(t), page_no, text.strip() if text and text.strip() else None))
    return sorted(events, key=lambda e: e.t)  # sorted는 안정 정렬 → 같은 t는 파일 순서


def build_plan(events: list[Event], start_page: int = 1) -> list[tuple[float, dict[str, Any]]]:
    """Event → (보낼 시각, WebSocket 메시지) 목록. 페이지가 바뀌면 page_change를 먼저 넣는다."""
    plan: list[tuple[float, dict[str, Any]]] = []
    current = start_page
    for e in events:
        if e.page_no != current:
            plan.append((e.t, {"type": "page_change", "page_no": e.page_no}))
            current = e.page_no
        if e.text:
            plan.append((e.t, {"type": "transcript", "page_no": e.page_no, "text": e.text, "final": True}))
    return plan


async def play(plan: list[tuple[float, dict[str, Any]]], send: Callable[[dict[str, Any]], Awaitable[None]],
               speed: float = 1.0, *, clock: Callable[[], float] = time.monotonic,
               sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
    """계획대로 메시지를 보낸다. 보내는 데 걸린 시간 때문에 밀리지 않도록 시작 시각 기준으로 잰다."""
    if speed <= 0:
        raise ValueError("speed는 0보다 커야 합니다")
    started = clock()
    for at, msg in plan:
        wait = started + at / speed - clock()
        if wait > 0:
            await sleep(wait)
        await send(msg)


# ---------- 실행 ----------
def _log(prefix: str, payload: Any) -> None:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    print(f"{datetime.now():%H:%M:%S} {prefix} {text}", flush=True)


def _summarize(msg: dict[str, Any]) -> str:
    if msg.get("type") == "page_update":
        lines = msg.get("easy_transcript") or []
        words = ", ".join(w["word"] for w in msg.get("hard_words") or [])
        last = lines[-1] if lines else ""
        return f"page_update {msg['page_no']}쪽 자막 {len(lines)}줄 · 최근: {last}" + (f" · 낱말: {words}" if words else "")
    if msg.get("type") == "ack":
        return ""  # 너무 많아서 생략
    return json.dumps(msg, ensure_ascii=False)


async def main(args: argparse.Namespace) -> None:
    import httpx
    import websockets

    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    plan = build_plan(load_events(data))
    total = plan[-1][0] / args.speed if plan else 0
    _log("●", f"{args.file}: 메시지 {len(plan)}개, 약 {total:.0f}초 ({args.speed}배속)")

    async with httpx.AsyncClient(base_url=args.server, timeout=30) as http:
        r = await http.post("/auth/login", json={"login_id": args.teacher, "password": args.password})
        if r.status_code != 200:
            raise SystemExit(f"로그인 실패: {r.status_code} {r.text}")
        token = r.json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        if args.start:
            r = await http.post(f"/lessons/{args.lesson}/start", headers=auth)
            if r.status_code != 200:
                raise SystemExit(f"수업 시작 실패: {r.status_code} {r.text}")
            _log("●", f"수업 시작 (status={r.json()['status']})")

        ws_url = args.server.replace("http", "ws", 1) + f"/ws/lessons/{args.lesson}?token={token}"
        async with websockets.connect(ws_url) as ws:
            async def receive() -> None:
                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("type") == "error":
                        _log("✕", msg)
                    elif summary := _summarize(msg):
                        _log("←", summary)

            async def send(msg: dict[str, Any]) -> None:
                await ws.send(json.dumps(msg, ensure_ascii=False))
                _log("→", f"[{msg['page_no']}쪽] " + (msg.get("text") or "페이지 이동"))

            receiver = asyncio.create_task(receive())
            try:
                await play(plan, send, args.speed)
                await asyncio.sleep(args.tail)
                if args.end:
                    r = await http.post(f"/lessons/{args.lesson}/end", headers=auth)
                    _log("●", f"수업 종료 ({r.status_code})")
                    await asyncio.sleep(args.tail)  # 종료 시 남은 발화 자막 대기
            finally:
                receiver.cancel()
    _log("●", "리플레이 끝")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file")
    p.add_argument("--lesson", type=int, required=True)
    p.add_argument("--teacher", default="teacher1")
    p.add_argument("--password", default="pass1234")
    p.add_argument("--server", default="http://localhost:8000")
    p.add_argument("--speed", type=float, default=1.0)
    p.add_argument("--start", action="store_true")
    p.add_argument("--end", action="store_true")
    p.add_argument("--tail", type=float, default=5.0)
    try:
        asyncio.run(main(p.parse_args()))
    except KeyboardInterrupt:
        pass
