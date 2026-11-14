import pytest

from tests.helpers import make_pdf, make_user
from tests.test_ws import ready_and_start, recv_until, ws_url

PDF = make_pdf(["1쪽 내용", "2쪽 내용"])
STROKE = {"tool": "pen", "color": "#e5484d", "width": 0.004, "points": [[0.1, 0.2], [0.3, 0.4]]}


@pytest.fixture()
def ctx(client):
    t1 = make_user(client, "tch1", "teacher")
    t2 = make_user(client, "tch2", "teacher")
    s1 = make_user(client, "stu1", "student")
    s2 = make_user(client, "stu2", "student")
    s3 = make_user(client, "stu3", "student")  # 미등록
    course = client.post("/courses", json={"name": "과학"}, headers=t1["headers"]).json()
    for s in (s1, s2):
        client.post("/courses/join", json={"invite_code": course["invite_code"]}, headers=s["headers"])
    lesson_id = client.post(f"/courses/{course['id']}/lessons", data={"session_no": "1", "title": "광합성"},
                            files={"file": ("a.pdf", PDF, "application/pdf")}, headers=t1["headers"]).json()["id"]
    tokens = {k: v["headers"]["Authorization"].split()[1] for k, v in
              {"t1": t1, "t2": t2, "s1": s1, "s2": s2}.items()}
    return {"t1": t1, "t2": t2, "s1": s1, "s2": s2, "s3": s3, "lesson_id": lesson_id, "tokens": tokens}


def url(ctx, page=None):
    base = f"/lessons/{ctx['lesson_id']}/annotations"
    return base if page is None else f"{base}/{page}"


def test_save_and_list_own_only(client, ctx):
    ready_and_start(client, ctx, start=False)
    r = client.put(url(ctx, 2), json={"strokes": [STROKE]}, headers=ctx["s1"]["headers"])
    assert r.status_code == 200
    assert r.json()["strokes"][0]["points"] == [[0.1, 0.2], [0.3, 0.4]]
    assert r.json()["updated_at"]
    client.put(url(ctx, 1), json={"strokes": [{**STROKE, "tool": "highlighter"}]}, headers=ctx["t1"]["headers"])

    pages = client.get(url(ctx), headers=ctx["s1"]["headers"]).json()["pages"]
    assert [p["page_no"] for p in pages] == [2]
    assert client.get(url(ctx), headers=ctx["s2"]["headers"]).json()["pages"] == []  # 다른 학생 필기는 안 보임
    teacher = client.get(url(ctx), headers=ctx["t1"]["headers"]).json()["pages"]
    assert [(p["page_no"], p["strokes"][0]["tool"]) for p in teacher] == [(1, "highlighter")]

    # 덮어쓰기, 빈 배열이면 삭제
    two = {"strokes": [STROKE, STROKE]}
    assert len(client.put(url(ctx, 2), json=two, headers=ctx["s1"]["headers"]).json()["strokes"]) == 2
    r = client.put(url(ctx, 2), json={"strokes": []}, headers=ctx["s1"]["headers"])
    assert r.json() == {"page_no": 2, "strokes": [], "updated_at": None}
    assert client.get(url(ctx), headers=ctx["s1"]["headers"]).json()["pages"] == []


def test_points_clamped_and_validation(client, ctx):
    ready_and_start(client, ctx, start=False)
    h = ctx["s1"]["headers"]
    r = client.put(url(ctx, 1), json={"strokes": [{**STROKE, "points": [[-0.2, 1.3]]}]}, headers=h)
    assert r.json()["strokes"][0]["points"] == [[0.0, 1.0]]
    for bad in ({**STROKE, "color": "red"}, {**STROKE, "tool": "laser"}, {**STROKE, "points": []},
                {**STROKE, "width": 0}):
        assert client.put(url(ctx, 1), json={"strokes": [bad]}, headers=h).status_code == 422
    assert client.put(url(ctx, 3), json={"strokes": [STROKE]}, headers=h).status_code == 404  # 없는 페이지
    assert client.put(url(ctx, 0), json={"strokes": [STROKE]}, headers=h).status_code == 422


def test_permissions(client, ctx):
    # 승인 전: 학생에게는 회차가 없는 것처럼 404, 교사는 가능
    assert client.get(url(ctx), headers=ctx["s1"]["headers"]).status_code == 404
    assert client.put(url(ctx, 1), json={"strokes": [STROKE]}, headers=ctx["t1"]["headers"]).status_code == 200
    ready_and_start(client, ctx, start=False)
    assert client.get(url(ctx), headers=ctx["s3"]["headers"]).status_code == 403  # 미등록 학생
    assert client.get(url(ctx), headers=ctx["t2"]["headers"]).status_code == 403  # 다른 교사
    assert client.get(url(ctx)).status_code in (401, 403)


def test_pointer_goes_to_students_only(client, ctx):
    ready_and_start(client, ctx)
    with client.websocket_connect(ws_url(ctx, "t1")) as t, client.websocket_connect(ws_url(ctx, "s1")) as s:
        recv_until(t, "teacher_page")
        recv_until(s, "teacher_page")
        t.send_json({"type": "pointer", "page_no": 2, "x": 0.5, "y": 0.25})
        msg, _ = recv_until(s, "pointer")
        assert msg == {"type": "pointer", "page_no": 2, "x": 0.5, "y": 0.25}
        t.send_json({"type": "pointer", "page_no": 2, "x": None, "y": None})  # 숨기기
        assert recv_until(s, "pointer")[0] == {"type": "pointer", "page_no": 2, "x": None, "y": None}

        # 교사에게는 pointer도 ack도 오지 않음 → 다음 ping의 응답이 바로 pong
        t.send_json({"type": "ping"})
        assert t.receive_json() == {"type": "pong"}

        t.send_json({"type": "pointer", "page_no": 2, "x": 1.5, "y": 0.2})
        assert t.receive_json()["type"] == "error"
        t.send_json({"type": "pointer", "page_no": 9, "x": 0.5, "y": 0.2})
        assert t.receive_json()["type"] == "error"
        s.send_json({"type": "pointer", "page_no": 1, "x": 0.5, "y": 0.2})
        assert s.receive_json()["type"] == "error"  # 학생은 보낼 수 없음
