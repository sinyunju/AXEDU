import asyncio
import json
from pathlib import Path

import pytest

from scripts.replay import Event, build_plan, load_events, play

SAMPLE = Path(__file__).parent.parent / "samples" / "replay_photosynthesis.json"


def test_sample_file_is_valid():
    events = load_events(json.loads(SAMPLE.read_text(encoding="utf-8")))
    assert len(events) == 18 and {e.page_no for e in events} == {1, 2, 3}
    plan = build_plan(events)
    assert [m["page_no"] for _, m in plan if m["type"] == "page_change"] == [2, 3]


def test_load_events_sorts_and_accepts_bare_list():
    events = load_events([
        {"t": 5, "page_no": 1, "text": "둘"},
        {"t": 0, "page_no": 1, "text": "하나"},
        {"t": 5, "page_no": 2},  # 같은 t는 파일 순서 유지
        {"t": 6, "page_no": 2, "text": "   "},  # 빈 발화 → 페이지 이동만
    ])
    assert events == [Event(0, 1, "하나"), Event(5, 1, "둘"), Event(5, 2, None), Event(6, 2, None)]


@pytest.mark.parametrize("data", [
    {}, {"events": []}, [1],
    [{"page_no": 1, "text": "x"}],  # t 없음
    [{"t": -1, "page_no": 1}],
    [{"t": True, "page_no": 1}],
    [{"t": 0, "page_no": 0}],
    [{"t": 0, "page_no": "1"}],
    [{"t": 0, "page_no": 1, "text": 3}],
])
def test_load_events_rejects_bad_input(data):
    with pytest.raises(ValueError):
        load_events(data)


def test_build_plan_inserts_page_changes():
    plan = build_plan([Event(0, 1, "a"), Event(1, 2, "b"), Event(2, 2, "c"), Event(3, 3, None), Event(4, 1, "d")])
    assert [(t, m["type"], m["page_no"], m.get("text")) for t, m in plan] == [
        (0, "transcript", 1, "a"),
        (1, "page_change", 2, None), (1, "transcript", 2, "b"),
        (2, "transcript", 2, "c"),
        (3, "page_change", 3, None),
        (4, "page_change", 1, None), (4, "transcript", 1, "d"),
    ]
    assert all(m["final"] is True for _, m in plan if m["type"] == "transcript")
    # 이미 다른 페이지에서 시작하는 경우
    assert build_plan([Event(0, 2, "x")], start_page=2)[0][1]["type"] == "transcript"


def test_play_timing_and_speed():
    now = [0.0]
    sent: list[tuple[float, str]] = []

    async def fake_sleep(sec):
        now[0] += sec

    async def send(msg):
        sent.append((now[0], msg["text"]))
        now[0] += 0.3  # 보내는 데 걸린 시간이 누적되어 밀리면 안 됨

    plan = [(0, {"text": "a"}), (10, {"text": "b"}), (10, {"text": "c"}), (30, {"text": "d"})]
    asyncio.run(play(plan, send, speed=2, clock=lambda: now[0], sleep=fake_sleep))
    assert sent == [(0, "a"), (5, "b"), (5.3, "c"), (15, "d")]

    with pytest.raises(ValueError):
        asyncio.run(play(plan, send, speed=0))
