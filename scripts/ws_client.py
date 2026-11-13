"""WebSocket 수동 테스트용 터미널 클라이언트.

  # 학생: 받은 메시지를 출력 (터미널 하나)
  .venv/bin/python -m scripts.ws_client student1 1

  # 교사: 입력한 줄을 발화(transcript)로 전송 (다른 터미널)
  .venv/bin/python -m scripts.ws_client teacher1 1
     그냥 입력      → {"type":"transcript","page_no":<현재 페이지>,"text":...,"final":true}
     /page 2        → {"type":"page_change","page_no":2}
     /ping          → {"type":"ping"}
     /raw {...}     → JSON 그대로 전송
     /quit          → 종료

서버 주소는 --server (기본 http://localhost:8000), 비밀번호는 --password (기본 시드 비밀번호 pass1234).
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime

import httpx
import websockets


def log(prefix: str, payload: object) -> None:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    print(f"{datetime.now():%H:%M:%S} {prefix} {text}", flush=True)


async def receiver(ws, state: dict) -> None:
    async for raw in ws:
        msg = json.loads(raw)
        if msg.get("type") == "teacher_page":
            state["page"] = msg["page_no"]
        log("←", msg)


async def sender(ws, state: dict) -> None:
    while True:
        line = (await asyncio.to_thread(sys.stdin.readline))
        if not line:  # EOF
            return
        line = line.strip()
        if not line:
            continue
        if line == "/quit":
            return
        if line == "/ping":
            msg = {"type": "ping"}
        elif line.startswith("/page "):
            msg = {"type": "page_change", "page_no": int(line.split()[1])}
            state["page"] = msg["page_no"]  # 서버 응답을 기다리지 않고 이후 발화에 바로 반영
        elif line.startswith("/raw "):
            msg = json.loads(line[5:])
        else:
            msg = {"type": "transcript", "page_no": state["page"], "text": line, "final": True}
        await ws.send(json.dumps(msg, ensure_ascii=False))
        log("→", msg)


async def main(args: argparse.Namespace) -> None:
    r = httpx.post(f"{args.server}/auth/login", json={"login_id": args.login_id, "password": args.password})
    if r.status_code != 200:
        raise SystemExit(f"로그인 실패: {r.status_code} {r.text}")
    data = r.json()
    role = data["user"]["role"]
    ws_url = args.server.replace("http", "ws", 1) + f"/ws/lessons/{args.lesson_id}?token={data['access_token']}"
    log("●", f"{args.login_id}({role}) → lesson {args.lesson_id} 연결 중")

    try:
        async with websockets.connect(ws_url) as ws:
            state = {"page": 1}
            tasks = [asyncio.create_task(receiver(ws, state))]
            if role == "teacher":
                print("발화를 입력하세요. (/page N, /ping, /raw {...}, /quit)", flush=True)
                tasks.append(asyncio.create_task(sender(ws, state)))
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            for t in done:
                if isinstance(t.exception(), websockets.ConnectionClosed):
                    raise t.exception()
    except websockets.ConnectionClosed as e:
        # 4401 토큰 무효, 4403 권한 없음, 4404 회차 없음/미승인
        log("✕", f"연결 종료 code={e.rcvd.code if e.rcvd else None} "
                 f"reason={e.rcvd.reason if e.rcvd else ''}")
        return
    log("✕", "연결 종료")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("login_id")
    p.add_argument("lesson_id", type=int)
    p.add_argument("--server", default="http://localhost:8000")
    p.add_argument("--password", default="pass1234")
    try:
        asyncio.run(main(p.parse_args()))
    except KeyboardInterrupt:
        pass
