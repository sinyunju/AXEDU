import asyncio

import pytest
from sqlmodel import select

from app.ai import AIError, get_ai_provider
from app.ai.mock import MockProvider
from app.models import Page, Quiz, QuizAttempt, Transcript
from app.services.quiz import QuizValidationError, grade, normalize_questions
from tests.helpers import make_pdf, make_user

PDF = make_pdf(["광합성이란? 식물이 빛으로 양분을 만드는 과정", "엽록체의 구조", "정리"])


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
    return {"t1": t1, "t2": t2, "s1": s1, "s2": s2, "s3": s3, "lesson_id": lesson_id}


def approve(client, ctx):
    h = ctx["t1"]["headers"]
    client.post(f"/lessons/{ctx['lesson_id']}/generate", headers=h)
    assert client.post(f"/lessons/{ctx['lesson_id']}/approve", headers=h).status_code == 200


def url(ctx, suffix=""):
    return f"/lessons/{ctx['lesson_id']}/quiz{suffix}"


def create(client, ctx, who="t1"):
    return client.post(url(ctx), headers=ctx[who]["headers"])


def submit(client, ctx, answers, who="s1"):
    body = {"answers": [{"question_id": q, "answer": a} for q, a in answers]}
    return client.post(url(ctx, "/attempts"), json=body, headers=ctx[who]["headers"])


# ---------- 생성 / 조회 ----------
def test_create_quiz(client, ctx):
    assert create(client, ctx).status_code == 409  # 승인 전
    approve(client, ctx)
    r = create(client, ctx)
    assert r.status_code == 201
    quiz = r.json()
    qs = quiz["questions"]
    assert [q["id"] for q in qs] == [1, 2, 3, 4, 5]
    assert {q["type"] for q in qs} == {"ox", "choice"}
    assert all(q["answer"] and q["explanation"] for q in qs)  # 교사에게는 정답·해설
    assert all(q["choices"] == ["O", "X"] for q in qs if q["type"] == "ox")
    assert all(len(q["choices"]) == 3 for q in qs if q["type"] == "choice")

    again = create(client, ctx)  # 이미 있으면 기존 것
    assert again.status_code == 200 and again.json()["id"] == quiz["id"]


def test_create_quiz_permissions(client, ctx):
    approve(client, ctx)
    assert create(client, ctx, "t2").status_code == 403
    assert create(client, ctx, "s1").status_code == 403
    assert client.post("/lessons/9999/quiz", headers=ctx["t1"]["headers"]).status_code == 404


def test_get_quiz_hides_answers_from_students(client, ctx):
    approve(client, ctx)
    assert client.get(url(ctx), headers=ctx["s1"]["headers"]).status_code == 404  # 아직 없음
    create(client, ctx)
    student = client.get(url(ctx), headers=ctx["s1"]["headers"])
    assert student.status_code == 200
    assert all(q["answer"] is None and q["explanation"] is None for q in student.json()["questions"])
    teacher = client.get(url(ctx), headers=ctx["t1"]["headers"]).json()
    assert all(q["answer"] for q in teacher["questions"])
    assert client.get(url(ctx), headers=ctx["s3"]["headers"]).status_code == 403  # 미등록
    assert client.get(url(ctx), headers=ctx["t2"]["headers"]).status_code == 403  # 다른 교사


def test_quiz_input_uses_approved_pages_and_transcripts(client, session, ctx):
    approve(client, ctx)
    page3 = session.exec(select(Page).where(Page.page_no == 3)).one()
    page3.approved = False  # 승인 해제된 페이지는 제외
    session.add(page3)
    session.add_all([Transcript(lesson_id=ctx["lesson_id"], page_no=1, text="광합성은 잎에서 일어나요"),
                     Transcript(lesson_id=ctx["lesson_id"], page_no=3, text="미승인 페이지 발화")])
    session.commit()

    seen = {}

    class Spy(MockProvider):
        async def generate_quiz(self, pages, transcripts):
            seen["pages"], seen["transcripts"] = pages, transcripts
            return await super().generate_quiz(pages, transcripts)

    client.app.dependency_overrides[get_ai_provider] = lambda: Spy()
    assert create(client, ctx).status_code == 201
    assert [p["page_no"] for p in seen["pages"]] == [1, 2]
    assert seen["pages"][0]["easy_sentences"]
    assert seen["transcripts"] == [{"page_no": 1, "text": "광합성은 잎에서 일어나요"}]


def test_create_quiz_ai_failures(client, session, ctx):
    approve(client, ctx)

    class Broken(MockProvider):
        async def generate_quiz(self, pages, transcripts):
            raise AIError("down")

    class Garbage(MockProvider):
        async def generate_quiz(self, pages, transcripts):
            return {"questions": [{"type": "choice", "question": "q", "choices": ["a", "b"], "answer": "a",
                                   "explanation": "", "page_no": 1}]}

    for provider in (Broken(), Garbage()):
        client.app.dependency_overrides[get_ai_provider] = lambda p=provider: p
        r = create(client, ctx)
        assert r.status_code == 502 and "detail" in r.json()
    assert session.exec(select(Quiz)).all() == []  # 실패하면 저장 안 함 → 다시 시도 가능


# ---------- 문항 정규화 ----------
def test_normalize_questions():
    raw = [
        {"type": "ox", "question": "물은 0도에서 얼어요.", "answer": "o", "explanation": "e", "page_no": 1},
        {"type": "OX", "question": "  ", "answer": "O", "page_no": 1},  # 빈 질문 → 버림
        {"type": "ox", "question": "q", "answer": "맞음", "page_no": 1},  # 정답 형식 오류 → 버림
        {"type": "choice", "question": "q2", "choices": ["가", "나", "다"], "answer": "라", "page_no": 2},  # 정답이 보기에 없음
        {"type": "choice", "question": "q3", "choices": ["가", "가", "다"], "answer": "가", "page_no": 2},  # 중복 보기
        {"type": "choice", "question": "q4", "choices": [" 가 ", "나", "다"], "answer": "가", "page_no": 99},
        {"type": "essay", "question": "q5", "answer": "x"},  # 지원하지 않는 유형
    ]
    out = normalize_questions(raw, {1, 2})
    assert [(q["id"], q["type"], q["answer"]) for q in out] == [(1, "ox", "O"), (2, "choice", "가")]
    assert out[0]["choices"] == ["O", "X"]
    assert sorted(out[1]["choices"]) == ["가", "나", "다"] and out[1]["page_no"] is None  # 잘못된 페이지 → None
    with pytest.raises(QuizValidationError):
        normalize_questions([{"type": "essay", "question": "q", "answer": "a"}], {1})


def test_grade():
    qs = normalize_questions([
        {"type": "ox", "question": "a", "answer": "O", "explanation": "e1", "page_no": 1},
        {"type": "choice", "question": "b", "choices": ["가", "나", "다"], "answer": "나", "explanation": "e2", "page_no": 1},
        {"type": "ox", "question": "c", "answer": "X", "explanation": "e3", "page_no": 1},
    ], {1})
    score, results = grade(qs, {1: "o", 2: "가"})
    assert score == 1
    assert [(r["answer"], r["correct"]) for r in results] == [("O", True), ("가", False), (None, False)]
    assert results[1]["correct_answer"] == "나" and results[1]["explanation"] == "e2"


# ---------- 제출 / 기록 ----------
def answer_key(client, ctx):
    return {q["id"]: q["answer"] for q in client.get(url(ctx), headers=ctx["t1"]["headers"]).json()["questions"]}


def test_submit_and_history(client, ctx):
    approve(client, ctx)
    create(client, ctx)
    key = answer_key(client, ctx)

    r = submit(client, ctx, list(key.items()))  # 전부 정답
    assert r.status_code == 201
    first = r.json()
    assert first["score"] == 5 and first["total"] == 5 and all(x["correct"] for x in first["results"])
    assert all(x["explanation"] for x in first["results"])  # 제출 후에는 해설 제공

    wrong = {1: "X" if key[1] == "O" else "O"}  # 1번만 틀리고 나머지는 안 풂
    second = submit(client, ctx, list(wrong.items())).json()
    assert second["score"] == 0 and second["total"] == 5
    assert second["results"][0]["correct_answer"] == key[1]
    assert second["results"][1]["answer"] is None

    history = client.get(url(ctx, "/attempts/me"), headers=ctx["s1"]["headers"]).json()
    assert [h["id"] for h in history] == [second["id"], first["id"]]  # 최신순


def test_attempt_records_are_private(client, session, ctx):
    approve(client, ctx)
    create(client, ctx)
    submit(client, ctx, [(1, "O")], who="s1")
    submit(client, ctx, [(1, "X")], who="s1")
    submit(client, ctx, [(1, "O")], who="s2")

    mine = client.get(url(ctx, "/attempts/me"), headers=ctx["s1"]["headers"]).json()
    theirs = client.get(url(ctx, "/attempts/me"), headers=ctx["s2"]["headers"]).json()
    assert len(mine) == 2 and len(theirs) == 1  # 다른 학생 기록은 보이지 않음
    assert {a.student_id for a in session.exec(select(QuizAttempt)).all()} == {ctx["s1"]["id"], ctx["s2"]["id"]}
    assert client.get(url(ctx, "/attempts/me"), headers=ctx["s3"]["headers"]).status_code == 403  # 미등록
    assert client.get(url(ctx, "/attempts/me"), headers=ctx["t1"]["headers"]).status_code == 403  # 교사


def test_submit_errors(client, ctx):
    approve(client, ctx)
    assert submit(client, ctx, [(1, "O")]).status_code == 404  # 퀴즈 없음
    create(client, ctx)
    key = answer_key(client, ctx)
    choice_id = next(q for q, a in key.items() if a not in ("O", "X"))

    assert submit(client, ctx, [(99, "O")]).status_code == 422  # 없는 문항
    assert submit(client, ctx, [(1, "O"), (1, "X")]).status_code == 422  # 중복
    assert submit(client, ctx, [(1, "맞아요")]).status_code == 422  # OX 형식 아님
    assert submit(client, ctx, [(choice_id, "보기에 없는 답")]).status_code == 422
    assert submit(client, ctx, [(1, "O")], who="t1").status_code == 403  # 교사 제출 불가
    assert submit(client, ctx, [(1, "O")], who="s3").status_code == 403  # 미등록
    assert submit(client, ctx, []).status_code == 201  # 빈 제출 → 0점 기록


def test_student_cannot_see_quiz_of_unapproved_lesson(client, ctx):
    # 승인 전 회차는 학생에게 존재 자체가 숨겨짐
    assert client.get(url(ctx), headers=ctx["s1"]["headers"]).status_code == 404
    assert client.get(url(ctx, "/attempts/me"), headers=ctx["s1"]["headers"]).status_code == 404


def test_choice_order_is_shuffled():
    raw = [{"type": "choice", "question": f"q{i}", "choices": ["정답", "오답1", "오답2"], "answer": "정답",
            "explanation": "", "page_no": 1} for i in range(10)]
    positions = set()
    for _ in range(5):
        for q in normalize_questions(raw, {1}):
            assert sorted(q["choices"]) == ["오답1", "오답2", "정답"] and q["answer"] == "정답"
            positions.add(q["choices"].index("정답"))
    assert positions == {0, 1, 2}  # 정답이 항상 첫 보기에 있지 않음
