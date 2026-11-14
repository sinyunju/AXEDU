import asyncio

import pytest
from sqlmodel import select

from app.ai import AIError, get_ai_provider, get_image_provider
from app.ai.base import AIProvider, ImageProvider
from app.ai.mock import MockProvider
from app.models import Lesson, LessonStatus, Page
from tests.helpers import make_pdf, make_user

PDF = make_pdf(["광합성이란? 식물이 빛으로 양분을 만드는 과정", "엽록체의 구조", ""])  # 3쪽은 빈 페이지


@pytest.fixture()
def ctx(client):
    t1 = make_user(client, "tch1", "teacher")
    t2 = make_user(client, "tch2", "teacher")
    s1 = make_user(client, "stu1", "student")
    course = client.post("/courses", json={"name": "과학"}, headers=t1["headers"]).json()
    client.post("/courses/join", json={"invite_code": course["invite_code"]}, headers=s1["headers"])
    r = client.post(f"/courses/{course['id']}/lessons", data={"session_no": "1", "title": "광합성"},
                    files={"file": ("a.pdf", PDF, "application/pdf")}, headers=t1["headers"])
    return {"t1": t1, "t2": t2, "s1": s1, "course": course, "lesson_id": r.json()["id"]}


def get_lesson(client, ctx, who="t1"):
    return client.get(f"/lessons/{ctx['lesson_id']}", headers=ctx[who]["headers"]).json()


def set_status(session, lesson_id, status):
    lesson = session.get(Lesson, lesson_id)
    lesson.status = status
    session.add(lesson)
    session.commit()


def generate(client, ctx, who="t1"):
    return client.post(f"/lessons/{ctx['lesson_id']}/generate", headers=ctx[who]["headers"])


# ---------- 재구성 ----------
def test_generate_flow(client, ctx):
    r = generate(client, ctx)
    assert r.status_code == 202
    assert r.json()["status"] == "generating" and r.json()["progress"] == 0 and r.json()["page_count"] == 3

    # TestClient는 백그라운드 작업이 끝난 뒤 반환한다
    lesson = get_lesson(client, ctx)
    assert lesson["status"] == "ready" and lesson["progress"] == 100
    p1, p2, p3 = lesson["pages"]
    assert p1["easy_sentences"] and p1["hard_words"]
    assert p1["image_suggestion"]["needed"] is True and p1["image_suggestion"]["prompt"]  # "과정" 포함 페이지
    assert p2["image_suggestion"]["needed"] is False
    assert p3["easy_sentences"] == [] and p3["image_suggestion"]["needed"] is False  # 빈 페이지
    assert not any(p["approved"] for p in lesson["pages"])


def test_generate_permissions_and_states(client, session, ctx):
    assert generate(client, ctx, "s1").status_code == 403
    assert generate(client, ctx, "t2").status_code == 403
    assert client.post("/lessons/9999/generate", headers=ctx["t1"]["headers"]).status_code == 404

    set_status(session, ctx["lesson_id"], LessonStatus.generating)
    assert generate(client, ctx).status_code == 409
    for st in (LessonStatus.approved, LessonStatus.live, LessonStatus.ended):
        set_status(session, ctx["lesson_id"], st)
        assert generate(client, ctx).status_code == 409
    set_status(session, ctx["lesson_id"], LessonStatus.ready)
    assert generate(client, ctx).status_code == 202  # ready에서는 다시 생성 가능


class _FailingOnPage2(MockProvider):
    def __init__(self):
        self.calls: list[str] = []

    async def restructure_page(self, source_text):
        self.calls.append(source_text)
        if "엽록체" in source_text:
            raise AIError("boom")
        return await super().restructure_page(source_text)


def test_generate_continues_after_page_failure(client, ctx):
    fake = _FailingOnPage2()
    client.app.dependency_overrides[get_ai_provider] = lambda: fake
    assert generate(client, ctx).status_code == 202
    lesson = get_lesson(client, ctx)
    assert lesson["status"] == "ready" and lesson["progress"] == 100
    assert lesson["pages"][0]["easy_sentences"]  # 1쪽 성공
    assert lesson["pages"][1]["easy_sentences"] == []  # 2쪽 실패 → 비어 있음
    assert len(fake.calls) == 2  # 빈 3쪽은 AI를 부르지 않음


def test_progress_is_updated_during_generation(client, session, ctx):
    from app.db import get_engine
    from app.services.generation import run_generation
    from sqlmodel import Session

    seen: list[int] = []

    class Spy(MockProvider):
        async def restructure_page(self, source_text):
            await asyncio.sleep(0.05)  # 앞서 끝난 결과를 메인 루프가 저장할 시간을 줌
            with Session(get_engine()) as s:
                seen.append(s.get(Lesson, ctx["lesson_id"]).progress)
            return await super().restructure_page(source_text)

    set_status(session, ctx["lesson_id"], LessonStatus.generating)
    asyncio.run(run_generation(ctx["lesson_id"], Spy(), concurrency=1))
    assert seen == [33, 66]  # 빈 3쪽이 먼저 끝나 33%, 1쪽 끝나 66%
    assert session.get(Lesson, ctx["lesson_id"]).progress == 100


def test_recover_stuck_generations(client, session, ctx):
    from app.services.generation import recover_stuck_generations

    set_status(session, ctx["lesson_id"], LessonStatus.generating)
    assert recover_stuck_generations() == 1
    session.expire_all()
    assert session.get(Lesson, ctx["lesson_id"]).status == LessonStatus.ready


# ---------- 페이지 수정 ----------
def test_update_page(client, session, ctx):
    url = f"/lessons/{ctx['lesson_id']}/pages/2"
    h = ctx["t1"]["headers"]
    r = client.put(url, json={"easy_sentences": ["  엽록체는 초록 알갱이예요. ", "", "잎에 있어요."]}, headers=h)
    assert r.status_code == 200
    assert r.json()["easy_sentences"] == ["엽록체는 초록 알갱이예요.", "잎에 있어요."]

    r = client.put(url, json={"hard_words": [{"word": "엽록체", "meaning": "잎 속 초록 알갱이"}]}, headers=h)
    assert r.json()["hard_words"] == [{"word": "엽록체", "meaning": "잎 속 초록 알갱이"}]
    assert r.json()["easy_sentences"] == ["엽록체는 초록 알갱이예요.", "잎에 있어요."]  # 보내지 않은 필드는 유지

    assert client.put(url, json={}, headers=h).status_code == 422
    assert client.put(url, json={"hard_words": [{"word": "x"}]}, headers=h).status_code == 422
    assert client.put(url, json={"easy_sentences": ["x"]}, headers=ctx["t2"]["headers"]).status_code == 403
    assert client.put(url, json={"easy_sentences": ["x"]}, headers=ctx["s1"]["headers"]).status_code == 403
    assert client.put(f"/lessons/{ctx['lesson_id']}/pages/99", json={"easy_sentences": ["x"]}, headers=h).status_code == 404

    set_status(session, ctx["lesson_id"], LessonStatus.generating)
    assert client.put(url, json={"easy_sentences": ["x"]}, headers=h).status_code == 409


# ---------- 이미지 ----------
def generated_files(tmp_path):
    d = tmp_path / "storage" / "generated"
    return sorted(d.iterdir()) if d.exists() else []


def test_image_from_suggestion_and_replace_and_delete(client, ctx, tmp_path):
    generate(client, ctx)
    h = ctx["t1"]["headers"]
    url = f"/lessons/{ctx['lesson_id']}/pages/1/image"

    r = client.post(url, headers=h)  # body 없이 → AI 제안 프롬프트 사용
    assert r.status_code == 200, r.text
    first = r.json()["generated_image_url"]
    assert first.startswith("/files/generated/") and first.endswith(".png")
    assert client.get(first).content.startswith(b"\x89PNG")

    r = client.post(url, json={"prompt": "잎에 햇빛이 비치는 모습"}, headers=h)  # 교사 지정 프롬프트로 교체
    assert r.json()["image_suggestion"]["prompt"] == "잎에 햇빛이 비치는 모습"
    assert r.json()["generated_image_url"] != first
    assert client.get(first).status_code == 404  # 이전 파일 삭제
    assert len(generated_files(tmp_path)) == 1

    r = client.delete(url, headers=h)
    assert r.status_code == 200
    assert r.json()["generated_image_url"] is None and r.json()["image_suggestion"] is None
    assert generated_files(tmp_path) == []


def test_image_errors(client, ctx):
    generate(client, ctx)
    h = ctx["t1"]["headers"]
    base = f"/lessons/{ctx['lesson_id']}/pages"
    r = client.post(f"{base}/2/image", json={}, headers=h)  # 2쪽은 제안 없음 + 프롬프트 없음
    assert r.status_code == 400
    assert client.post(f"{base}/2/image", json={"prompt": "엽록체"}, headers=h).status_code == 200
    assert client.post(f"{base}/1/image", headers=ctx["t2"]["headers"]).status_code == 403
    assert client.post(f"{base}/1/image", headers=ctx["s1"]["headers"]).status_code == 403
    assert client.post(f"{base}/99/image", json={"prompt": "x"}, headers=h).status_code == 404

    class Broken(ImageProvider):
        async def generate_image(self, prompt):
            raise AIError("gateway down")

    client.app.dependency_overrides[get_image_provider] = lambda: Broken()
    r = client.post(f"{base}/1/image", headers=h)
    assert r.status_code == 502 and "detail" in r.json()


# ---------- 승인 ----------
def test_approve_flow(client, session, ctx):
    url = f"/lessons/{ctx['lesson_id']}/approve"
    h = ctx["t1"]["headers"]
    assert client.post(url, headers=h).status_code == 409  # 재구성 전
    generate(client, ctx)
    assert client.post(url, headers=ctx["t2"]["headers"]).status_code == 403
    assert client.post(url, headers=ctx["s1"]["headers"]).status_code == 403

    r = client.post(url, headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "approved" and all(p["approved"] for p in r.json()["pages"])
    assert client.post(url, headers=h).status_code == 200  # 재승인은 그대로 성공

    # 학생에게 공개됨
    student = get_lesson(client, ctx, "s1")
    assert student["status"] == "approved" and student["pages"][0]["easy_sentences"]
    course = client.get(f"/courses/{ctx['course']['id']}", headers=ctx["s1"]["headers"]).json()
    assert [l["id"] for l in course["lessons"]] == [ctx["lesson_id"]]

    set_status(session, ctx["lesson_id"], LessonStatus.live)
    assert client.post(url, headers=h).status_code == 409


def test_generation_finishes_even_if_status_was_recovered_meanwhile(client, session, ctx):
    """다른 프로세스가 시작하며 진행 중 회차를 ready로 바꿔도 끝나면 progress=100."""
    from sqlmodel import Session as S

    from app.db import get_engine
    from app.services.generation import recover_stuck_generations, run_generation

    class RecoversMidway(MockProvider):
        async def restructure_page(self, source_text):
            recover_stuck_generations()  # 작업 도중 다른 프로세스의 시작 처리가 끼어든 상황
            return await super().restructure_page(source_text)

    set_status(session, ctx["lesson_id"], LessonStatus.generating)
    asyncio.run(run_generation(ctx["lesson_id"], RecoversMidway(), concurrency=1))
    with S(get_engine()) as s:
        lesson = s.get(Lesson, ctx["lesson_id"])
        assert lesson.status == LessonStatus.ready and lesson.progress == 100


def test_image_prompt_is_translated_before_generation(client, ctx):
    """이미지 모델에는 영어로 바꾼 프롬프트를 보내고, 교사에게 보이는 제안 프롬프트는 한국어 그대로."""
    from app.ai import get_ai_provider
    from app.ai.mock import MockProvider

    generate(client, ctx)
    sent = []

    class Translating(MockProvider):
        async def image_prompt(self, description):
            return f"EN: {description}"

    class Recording(ImageProvider):
        async def generate_image(self, prompt):
            sent.append(prompt)
            return b"\x89PNG\r\n\x1a\n" + b"0" * 20

    class BrokenTranslator(MockProvider):
        async def image_prompt(self, description):
            raise AIError("down")

    client.app.dependency_overrides[get_ai_provider] = lambda: Translating()
    client.app.dependency_overrides[get_image_provider] = lambda: Recording()
    try:
        base = f"/lessons/{ctx['lesson_id']}/pages"
        r = client.post(f"{base}/2/image", json={"prompt": "초록 잎"}, headers=ctx["t1"]["headers"])
        assert r.status_code == 200
        assert sent == ["EN: 초록 잎"]
        assert r.json()["image_suggestion"]["prompt"] == "초록 잎"
        # 번역이 실패해도 원문으로 시도
        client.app.dependency_overrides[get_ai_provider] = lambda: BrokenTranslator()
        assert client.post(f"{base}/2/image", json={"prompt": "초록 잎"}, headers=ctx["t1"]["headers"]).status_code == 200
        assert sent[-1] == "초록 잎"
    finally:
        client.app.dependency_overrides.pop(get_ai_provider, None)
        client.app.dependency_overrides.pop(get_image_provider, None)
