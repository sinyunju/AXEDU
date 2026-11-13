import pytest
from sqlmodel import select

from app.ai import AIError, get_ai_provider
from app.ai.mock import MockProvider
from app.models import ChatMessage, Page, Transcript
from tests.helpers import make_pdf, make_user

PDF = make_pdf(["광합성이란? 식물이 빛으로 양분을 만드는 과정", "엽록체의 구조", "정리"])


@pytest.fixture()
def ctx(client):
    t1 = make_user(client, "tch1", "teacher")
    s1 = make_user(client, "stu1", "student")
    s2 = make_user(client, "stu2", "student")
    s3 = make_user(client, "stu3", "student")  # 미등록
    course = client.post("/courses", json={"name": "과학"}, headers=t1["headers"]).json()
    for s in (s1, s2):
        client.post("/courses/join", json={"invite_code": course["invite_code"]}, headers=s["headers"])
    lesson_id = client.post(f"/courses/{course['id']}/lessons", data={"session_no": "1", "title": "광합성"},
                            files={"file": ("a.pdf", PDF, "application/pdf")}, headers=t1["headers"]).json()["id"]
    return {"t1": t1, "s1": s1, "s2": s2, "s3": s3, "lesson_id": lesson_id}


def approve(client, ctx):
    h = ctx["t1"]["headers"]
    client.post(f"/lessons/{ctx['lesson_id']}/generate", headers=h)
    assert client.post(f"/lessons/{ctx['lesson_id']}/approve", headers=h).status_code == 200


def ask(client, ctx, message, who="s1"):
    return client.post(f"/lessons/{ctx['lesson_id']}/chat", json={"message": message}, headers=ctx[who]["headers"])


def history(client, ctx, who="s1"):
    return client.get(f"/lessons/{ctx['lesson_id']}/chat", headers=ctx[who]["headers"])


class Spy(MockProvider):
    def __init__(self, related_page=1, kind="lesson", answer=None):
        self.calls = []
        self.related_page = related_page
        self.kind = kind
        self.answer = answer

    async def chat(self, pages, transcripts, history, message):
        self.calls.append({"pages": pages, "transcripts": transcripts, "history": history, "message": message})
        return {"kind": self.kind, "answer": self.answer or f"답{len(self.calls)}", "related_page": self.related_page}


def use(client, provider):
    client.app.dependency_overrides[get_ai_provider] = lambda: provider
    return provider


# ---------- 질문 / 기록 ----------
def test_ask_and_history(client, ctx):
    approve(client, ctx)
    r = ask(client, ctx, "  광합성이 뭐예요?  ")
    assert r.status_code == 200
    q, a = r.json()["question"], r.json()["answer"]
    assert q["role"] == "user" and q["content"] == "광합성이 뭐예요?" and q["related_page"] is None
    assert a["role"] == "assistant" and a["content"] and a["related_page"] == 1

    off = ask(client, ctx, "축구 좋아해?").json()["answer"]  # mock: 수업과 무관
    assert off["content"].startswith("이건 오늘 수업과 다른 이야기예요") and off["related_page"] is None

    h = history(client, ctx).json()
    assert [(m["role"], m["content"]) for m in h][:3] == [
        ("user", "광합성이 뭐예요?"), ("assistant", a["content"]), ("user", "축구 좋아해?")]
    assert len(h) == 4 and [m["id"] for m in h] == sorted(m["id"] for m in h)


def test_context_is_approved_content_and_own_recent_history(client, session, ctx, monkeypatch):
    approve(client, ctx)
    page3 = session.exec(select(Page).where(Page.page_no == 3)).one()
    page3.approved = False
    session.add(page3)
    session.add(Transcript(lesson_id=ctx["lesson_id"], page_no=2, text="엽록체는 초록색이에요"))
    session.commit()
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "chat_history_limit", 4)
    spy = use(client, Spy())

    ask(client, ctx, "다른 학생 질문", who="s2")  # 다른 학생 대화는 문맥에 섞이지 않아야 함
    for i in range(1, 4):
        ask(client, ctx, f"질문{i}")

    last = spy.calls[-1]
    assert [p["page_no"] for p in last["pages"]] == [1, 2]  # 승인된 페이지만
    assert last["transcripts"] == [{"page_no": 2, "text": "엽록체는 초록색이에요"}]
    assert last["message"] == "질문3"
    # s1의 최근 4개 (질문1, 답2, 질문2, 답3) — 오래된 것부터, s2 대화 없음
    assert last["history"] == [
        {"role": "user", "content": "질문1"}, {"role": "assistant", "content": "답2"},
        {"role": "user", "content": "질문2"}, {"role": "assistant", "content": "답3"},
    ]
    assert spy.calls[1]["history"] == []  # s1의 첫 질문엔 이전 대화 없음


def test_invalid_related_page_becomes_none(client, ctx):
    approve(client, ctx)
    use(client, Spy(related_page=99))
    assert ask(client, ctx, "질문").json()["answer"]["related_page"] is None


def test_ai_failure_saves_nothing(client, session, ctx):
    approve(client, ctx)

    class Broken(MockProvider):
        async def chat(self, *a):
            raise AIError("down")

    use(client, Broken())
    r = ask(client, ctx, "광합성이 뭐예요?")
    assert r.status_code == 502 and "detail" in r.json()
    assert session.exec(select(ChatMessage)).all() == []


# ---------- 권한 / 검증 ----------
def test_chat_records_are_private(client, ctx):
    approve(client, ctx)
    ask(client, ctx, "광합성이 뭐예요?", who="s1")
    assert len(history(client, ctx, "s1").json()) == 2
    assert history(client, ctx, "s2").json() == []  # 다른 학생 대화는 보이지 않음
    assert history(client, ctx, "s3").status_code == 403  # 미등록 학생
    assert history(client, ctx, "t1").status_code == 403  # 교사도 학생 대화 조회 불가
    assert ask(client, ctx, "질문", who="t1").status_code == 403
    assert ask(client, ctx, "질문", who="s3").status_code == 403


def test_chat_unapproved_lesson_and_validation(client, ctx):
    assert ask(client, ctx, "광합성이 뭐예요?").status_code == 404  # 미승인 회차는 숨김
    assert history(client, ctx).status_code == 404
    approve(client, ctx)
    assert ask(client, ctx, "").status_code == 422
    assert ask(client, ctx, "   ").status_code == 422
    assert ask(client, ctx, "가" * 501).status_code == 422
    assert client.post("/lessons/9999/chat", json={"message": "x"}, headers=ctx["s1"]["headers"]).status_code == 404


# ---------- 4분류 후처리 (서버에서 강제) ----------
NOT_COVERED = "오늘 수업에서는 거기까지 나오지 않았어요. 선생님께 물어보면 알려 주실 거예요."
OFF_TOPIC = "이건 오늘 수업과 다른 이야기예요. 수업 내용을 물어봐 줄래요?"


@pytest.mark.parametrize("result, expected", [
    ({"kind": "lesson", "answer": "재료는 물이에요.", "related_page": 1}, ("재료는 물이에요.", 1)),
    ({"kind": "lesson", "answer": "a", "related_page": 99}, ("a", None)),  # 없는 페이지 → None
    # 기초 질문: 근거 페이지가 있으면 그대로
    ({"kind": "basic", "answer": "엽록체에서 일어나요.", "related_page": 2}, ("엽록체에서 일어나요.", 2)),
    # 기초 질문인데 근거 페이지가 없거나 틀리면 → 심화 문구
    ({"kind": "basic", "answer": "엽록체에서 일어나요.", "related_page": None}, (NOT_COVERED, None)),
    ({"kind": "basic", "answer": "엽록체에서 일어나요.", "related_page": 99}, (NOT_COVERED, None)),
    # 정해진 문구로 통일
    ({"kind": "not_covered", "answer": "몰라요", "related_page": 1}, (NOT_COVERED, 1)),
    ({"kind": "off_topic", "answer": "다른 이야기", "related_page": 1}, (OFF_TOPIC, None)),
    ({"kind": "care", "answer": "어른에게 이야기해 주세요.", "related_page": 1}, ("어른에게 이야기해 주세요.", None)),
    ({"answer": "kind 없음", "related_page": 1}, ("kind 없음", 1)),
])
def test_finalize_chat(result, expected):
    from app.services.chat import finalize_chat

    assert finalize_chat(result, {1, 2, 3}) == expected


def test_basic_answer_without_page_is_saved_as_not_covered(client, ctx):
    approve(client, ctx)
    use(client, Spy(kind="basic", related_page=None, answer="광합성은 엽록체에서 일어나요."))
    a = ask(client, ctx, "광합성은 어디에서 일어나요?").json()["answer"]
    assert a["content"] == NOT_COVERED and a["related_page"] is None
    assert history(client, ctx).json()[1]["content"] == NOT_COVERED  # 저장도 바뀐 문구로

    use(client, Spy(kind="basic", related_page=2, answer="광합성은 엽록체에서 일어나요."))
    a = ask(client, ctx, "광합성은 어디에서 일어나요?").json()["answer"]
    assert a["content"] == "광합성은 엽록체에서 일어나요." and a["related_page"] == 2
