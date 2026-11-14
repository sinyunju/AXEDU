import pytest
from sqlmodel import select

from app.models import Lesson, LessonStatus, Page
from tests.helpers import make_pdf, make_user

PDF = make_pdf(["광합성이란 무엇인가", "엽록체의 구조", "정리"])


@pytest.fixture()
def ctx(client):
    t1 = make_user(client, "tch1", "teacher")
    t2 = make_user(client, "tch2", "teacher")
    s1 = make_user(client, "stu1", "student")
    s2 = make_user(client, "stu2", "student")
    course = client.post("/courses", json={"name": "과학"}, headers=t1["headers"]).json()
    client.post("/courses/join", json={"invite_code": course["invite_code"]}, headers=s1["headers"])
    return {"t1": t1, "t2": t2, "s1": s1, "s2": s2, "course": course}


def upload(client, user, course_id, *, pdf=PDF, session_no=1, title="1회차 광합성", class_date=None,
           filename="lesson.pdf"):
    data = {"session_no": str(session_no), "title": title}
    if class_date:
        data["class_date"] = class_date
    return client.post(f"/courses/{course_id}/lessons", data=data,
                       files={"file": (filename, pdf, "application/pdf")}, headers=user["headers"])


def stored_pngs(tmp_path):
    d = tmp_path / "storage" / "pages"
    return sorted(d.glob("*.png")) if d.exists() else []


# ---------- 업로드 ----------
def test_upload_splits_and_renders(client, ctx, tmp_path):
    r = upload(client, ctx["t1"], ctx["course"]["id"], class_date="2026-11-20")
    assert r.status_code == 201, r.text
    lesson = r.json()
    assert lesson["status"] == "uploaded" and lesson["progress"] == 0
    assert lesson["page_count"] == 3 and lesson["class_date"] == "2026-11-20"
    assert [p["page_no"] for p in lesson["pages"]] == [1, 2, 3]
    assert lesson["pages"][0]["source_text"] == "광합성이란 무엇인가"
    assert lesson["pages"][1]["source_text"] == "엽록체의 구조"

    # PNG가 실제로 저장되고 /files 로 제공되는지
    assert len(stored_pngs(tmp_path)) == 3
    url = lesson["pages"][0]["image_url"]
    assert url.startswith("/files/pages/") and len(url.rsplit("/", 1)[1]) == 32 + 4  # uuid hex + .png
    img = client.get(url)
    assert img.status_code == 200 and img.content.startswith(b"\x89PNG")

    # 과목 상세의 회차 목록에도 보임
    detail = client.get(f"/courses/{ctx['course']['id']}", headers=ctx["t1"]["headers"]).json()
    assert [l["title"] for l in detail["lessons"]] == ["1회차 광합성"]


def test_upload_permissions(client, ctx):
    cid = ctx["course"]["id"]
    assert upload(client, ctx["s1"], cid).status_code == 403  # 학생
    assert upload(client, ctx["t2"], cid).status_code == 403  # 다른 교사
    assert upload(client, ctx["t1"], 9999).status_code == 404


def test_upload_rejects_bad_files_without_leftovers(client, ctx, tmp_path):
    cid = ctx["course"]["id"]
    r = upload(client, ctx["t1"], cid, pdf=b"hello", filename="a.txt")
    assert r.status_code == 400 and "PDF" in r.json()["detail"]
    assert upload(client, ctx["t1"], cid, pdf=b"%PDF-1.7 broken").status_code == 400
    assert stored_pngs(tmp_path) == []
    assert client.get(f"/courses/{cid}", headers=ctx["t1"]["headers"]).json()["lessons"] == []


def test_upload_limits(client, ctx, tmp_path, monkeypatch):
    from app.config import get_settings

    cid = ctx["course"]["id"]
    monkeypatch.setattr(get_settings(), "max_pdf_pages", 2)
    r = upload(client, ctx["t1"], cid)
    assert r.status_code == 400 and "최대 2페이지" in r.json()["detail"]

    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    assert upload(client, ctx["t1"], cid).status_code == 413
    assert stored_pngs(tmp_path) == []


def test_upload_validation(client, ctx):
    cid = ctx["course"]["id"]
    assert upload(client, ctx["t1"], cid, session_no=0).status_code == 422
    assert upload(client, ctx["t1"], cid, title="").status_code == 422
    assert upload(client, ctx["t1"], cid, class_date="내일").status_code == 422
    r = client.post(f"/courses/{cid}/lessons", data={"session_no": "1", "title": "x"}, headers=ctx["t1"]["headers"])
    assert r.status_code == 422  # 파일 없음


def test_duplicate_session_no(client, ctx, tmp_path):
    cid = ctx["course"]["id"]
    assert upload(client, ctx["t1"], cid, session_no=1).status_code == 201
    r = upload(client, ctx["t1"], cid, session_no=1)
    assert r.status_code == 409
    assert len(stored_pngs(tmp_path)) == 3  # 두 번째 업로드는 파일을 남기지 않음
    assert upload(client, ctx["t1"], cid, session_no=2).status_code == 201
    # 다른 과목은 같은 회차 번호 사용 가능
    other = client.post("/courses", json={"name": "수학"}, headers=ctx["t1"]["headers"]).json()
    assert upload(client, ctx["t1"], other["id"], session_no=1).status_code == 201


# ---------- 조회 ----------
def test_get_lesson_permissions(client, ctx):
    lesson = upload(client, ctx["t1"], ctx["course"]["id"]).json()
    url = f"/lessons/{lesson['id']}"
    assert client.get(url, headers=ctx["t1"]["headers"]).status_code == 200
    assert client.get(url, headers=ctx["t2"]["headers"]).status_code == 403  # 다른 교사
    assert client.get(url, headers=ctx["s2"]["headers"]).status_code == 403  # 미등록 학생
    assert client.get(url, headers=ctx["s1"]["headers"]).status_code == 404  # 등록했지만 미승인 회차
    assert client.get("/lessons/9999", headers=ctx["t1"]["headers"]).status_code == 404
    assert client.get(url).status_code == 401


def test_student_view_hides_unapproved_content(client, session, ctx):
    lesson_id = upload(client, ctx["t1"], ctx["course"]["id"]).json()["id"]
    # 5단계(재구성·승인) 전이므로 DB에서 직접 상태를 만든다
    for p in session.exec(select(Page).where(Page.lesson_id == lesson_id)).all():
        p.easy_sentences = [f"{p.page_no}쪽 쉬운 문장"]
        p.hard_words = [{"word": "엽록체", "meaning": "잎 속 초록 알갱이"}]
        p.image_suggestion = {"needed": False, "reason": "", "prompt": ""}
        p.approved = p.page_no != 3  # 3쪽만 미승인
        session.add(p)
    lesson = session.get(Lesson, lesson_id)
    lesson.status = LessonStatus.approved
    session.add(lesson)
    session.commit()

    teacher = client.get(f"/lessons/{lesson_id}", headers=ctx["t1"]["headers"]).json()
    assert teacher["pages"][2]["easy_sentences"] == ["3쪽 쉬운 문장"]
    assert teacher["pages"][0]["source_text"] and teacher["pages"][0]["image_suggestion"]["needed"] is False

    r = client.get(f"/lessons/{lesson_id}", headers=ctx["s1"]["headers"])
    assert r.status_code == 200
    pages = r.json()["pages"]
    assert pages[0]["easy_sentences"] == ["1쪽 쉬운 문장"]
    assert pages[0]["hard_words"][0]["word"] == "엽록체"
    assert pages[2]["easy_sentences"] == [] and pages[2]["hard_words"] == []  # 미승인 페이지
    assert all(p["source_text"] is None and p["image_suggestion"] is None for p in pages)
    assert all(p["image_url"].startswith("/files/") for p in pages)  # 원본 이미지는 항상 제공


# ---------- 낱말 뜻 AI ----------
def test_explain_term(client, ctx):
    from app.ai import AIError, get_ai_provider
    from app.ai.mock import MockProvider

    lesson_id = upload(client, ctx["t1"], ctx["course"]["id"]).json()["id"]
    url = f"/lessons/{lesson_id}/pages/1/terms/explain"
    seen = {}

    class Recording(MockProvider):
        async def explain_term(self, source_text, word):
            seen.update(source_text=source_text, word=word)
            return {"meaning": "잎 속에서 빛으로 양분을 만드는 알갱이예요."}

    client.app.dependency_overrides[get_ai_provider] = lambda: Recording()
    try:
        r = client.post(url, json={"word": "  엽록체 "}, headers=ctx["t1"]["headers"])
        assert r.status_code == 200
        assert r.json() == {"word": "엽록체", "meaning": "잎 속에서 빛으로 양분을 만드는 알갱이예요."}
        assert seen["word"] == "엽록체" and seen["source_text"]  # 그 페이지 글을 문맥으로 넘김

        class Broken(MockProvider):
            async def explain_term(self, source_text, word):
                raise AIError("down")

        client.app.dependency_overrides[get_ai_provider] = lambda: Broken()
        assert client.post(url, json={"word": "엽록체"}, headers=ctx["t1"]["headers"]).status_code == 502
    finally:
        client.app.dependency_overrides.pop(get_ai_provider, None)

    # MOCK_AI 고정 응답
    assert client.post(url, json={"word": "엽록체"}, headers=ctx["t1"]["headers"]).json()["meaning"]
    # 권한·입력 검증
    assert client.post(url, json={"word": "엽록체"}, headers=ctx["t2"]["headers"]).status_code == 403
    assert client.post(url, json={"word": "엽록체"}, headers=ctx["s1"]["headers"]).status_code == 403
    assert client.post(f"/lessons/{lesson_id}/pages/99/terms/explain", json={"word": "a"},
                       headers=ctx["t1"]["headers"]).status_code == 404
    for bad in ({"word": "   "}, {"word": ""}, {"word": "가" * 41}, {}):
        assert client.post(url, json=bad, headers=ctx["t1"]["headers"]).status_code == 422


# ---------- 회차 정보 수정 ----------
def test_update_lesson_info(client, ctx):
    cid = ctx["course"]["id"]
    first = upload(client, ctx["t1"], cid, session_no=1, title="광합성", class_date="2026-11-20").json()
    upload(client, ctx["t1"], cid, session_no=2, title="호흡")
    url = f"/lessons/{first['id']}"
    h = ctx["t1"]["headers"]

    r = client.patch(url, json={"title": "  광합성 (1) ", "session_no": 3}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "광합성 (1)" and body["session_no"] == 3 and body["class_date"] == "2026-11-20"
    assert body["page_count"] == first["page_count"]  # 자료는 그대로
    # 날짜 변경·삭제 (null), 안 보내면 그대로
    assert client.patch(url, json={"class_date": "2026-12-01"}, headers=h).json()["class_date"] == "2026-12-01"
    assert client.patch(url, json={"title": "광합성"}, headers=h).json()["class_date"] == "2026-12-01"
    assert client.patch(url, json={"class_date": None}, headers=h).json()["class_date"] is None
    # 같은 번호로 바꾸는 건 괜찮고, 다른 회차 번호와 겹치면 409
    assert client.patch(url, json={"session_no": 3}, headers=h).status_code == 200
    assert client.patch(url, json={"session_no": 2}, headers=h).status_code == 409
    courses = client.get(f"/courses/{cid}", headers=h).json()["lessons"]
    assert sorted((l["session_no"], l["title"]) for l in courses) == [(2, "호흡"), (3, "광합성")]

    for bad in ({"title": "  "}, {"session_no": 0}, {"class_date": "2026-11-20T10:00:00"}, {"title": "가" * 201}):
        assert client.patch(url, json=bad, headers=h).status_code == 422
    assert client.patch(url, json={"title": "x"}, headers=ctx["t2"]["headers"]).status_code == 403
    assert client.patch(url, json={"title": "x"}, headers=ctx["s1"]["headers"]).status_code == 403
    assert client.patch("/lessons/9999", json={"title": "x"}, headers=h).status_code == 404
