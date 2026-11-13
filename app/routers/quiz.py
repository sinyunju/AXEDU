from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.ai import AIError, AIProvider, get_ai_provider
from app.db import get_session
from app.deps import get_current_user, require_student, require_teacher
from app.models import Lesson, LessonStatus, Quiz, QuizAttempt, Role, User
from app.permissions import get_accessible_lesson, get_owned_lesson
from app.schemas import AttemptCreate, AttemptOut, QuizOut, QuizQuestionOut
from app.services.content import lesson_content
from app.services.quiz import QuizValidationError, check_answers, grade, normalize_questions

router = APIRouter(tags=["quiz"])

_QUIZ_READY = (LessonStatus.approved, LessonStatus.live, LessonStatus.ended)


def _quiz_out(quiz: Quiz, viewer: User) -> QuizOut:
    show = viewer.role == Role.teacher
    return QuizOut(
        id=quiz.id, lesson_id=quiz.lesson_id,
        questions=[
            QuizQuestionOut(
                id=q["id"], type=q["type"], question=q["question"], choices=q["choices"], page_no=q["page_no"],
                answer=q["answer"] if show else None, explanation=q["explanation"] if show else None,
            )
            for q in quiz.questions
        ],
    )


def _get_quiz(session: Session, lesson: Lesson) -> Quiz | None:
    return session.exec(select(Quiz).where(Quiz.lesson_id == lesson.id)).first()


def _attempt_out(attempt: QuizAttempt) -> AttemptOut:
    return AttemptOut(id=attempt.id, quiz_id=attempt.quiz_id, score=attempt.score, total=len(attempt.answers),
                      submitted_at=attempt.submitted_at, results=attempt.answers)


@router.post(
    "/lessons/{lesson_id}/quiz",
    response_model=QuizOut,
    status_code=status.HTTP_201_CREATED,
    summary="퀴즈 생성 (교사)",
    description="승인된 페이지 내용과 교사 발화로 OX/3지선다 5문항 안팎을 만든다. 이미 있으면 기존 퀴즈를 200으로 반환.",
    responses={200: {"description": "이미 만든 퀴즈"}, 409: {"description": "승인 전 회차"},
               502: {"description": "AI 생성 실패"}},
)
async def create_quiz(
    lesson_id: int, response: Response,
    session: Session = Depends(get_session), teacher: User = Depends(require_teacher),
    provider: AIProvider = Depends(get_ai_provider),
) -> QuizOut:
    lesson = get_owned_lesson(session, lesson_id, teacher)
    if (existing := _get_quiz(session, lesson)) is not None:
        response.status_code = status.HTTP_200_OK
        return _quiz_out(existing, teacher)
    if lesson.status not in _QUIZ_READY:
        raise HTTPException(status.HTTP_409_CONFLICT, "승인한 회차만 퀴즈를 만들 수 있습니다")

    pages, transcripts = lesson_content(session, lesson.id)
    try:
        raw = await provider.generate_quiz(pages, transcripts)
        questions = normalize_questions(raw.get("questions", []), {p["page_no"] for p in pages})
    except (AIError, QuizValidationError) as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"퀴즈를 만들지 못했습니다. 다시 시도해 주세요 ({e})")

    quiz = Quiz(lesson_id=lesson.id, questions=questions)
    session.add(quiz)
    try:
        session.commit()
    except IntegrityError:  # 동시에 두 번 눌러 먼저 만들어진 경우
        session.rollback()
        response.status_code = status.HTTP_200_OK
        return _quiz_out(_get_quiz(session, lesson), teacher)
    session.refresh(quiz)
    return _quiz_out(quiz, teacher)


@router.get("/lessons/{lesson_id}/quiz", response_model=QuizOut, summary="퀴즈 조회 (학생에게는 정답·해설 제외)")
def get_quiz(
    lesson_id: int, session: Session = Depends(get_session), user: User = Depends(get_current_user),
) -> QuizOut:
    lesson = get_accessible_lesson(session, lesson_id, user)
    quiz = _get_quiz(session, lesson)
    if quiz is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "아직 퀴즈가 없습니다")
    return _quiz_out(quiz, user)


@router.post(
    "/lessons/{lesson_id}/quiz/attempts",
    response_model=AttemptOut,
    status_code=status.HTTP_201_CREATED,
    summary="퀴즈 제출·채점 (학생)",
    description="채점 결과와 해설을 저장하고 반환한다. 여러 번 제출할 수 있고, 제출할 때마다 기록이 쌓인다.",
)
def submit_attempt(
    lesson_id: int, body: AttemptCreate,
    session: Session = Depends(get_session), student: User = Depends(require_student),
) -> AttemptOut:
    lesson = get_accessible_lesson(session, lesson_id, student)
    quiz = _get_quiz(session, lesson)
    if quiz is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "아직 퀴즈가 없습니다")
    try:
        answers = check_answers(quiz.questions, [(a.question_id, a.answer) for a in body.answers])
    except QuizValidationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))
    score, results = grade(quiz.questions, answers)
    attempt = QuizAttempt(quiz_id=quiz.id, student_id=student.id, answers=results, score=score)
    session.add(attempt)
    session.commit()
    session.refresh(attempt)
    return _attempt_out(attempt)


@router.get("/lessons/{lesson_id}/quiz/attempts/me", response_model=list[AttemptOut],
            summary="내 풀이 기록 (학생, 최신순)")
def my_attempts(
    lesson_id: int, session: Session = Depends(get_session), student: User = Depends(require_student),
) -> list[AttemptOut]:
    lesson = get_accessible_lesson(session, lesson_id, student)
    quiz = _get_quiz(session, lesson)
    if quiz is None:
        return []
    attempts = session.exec(
        select(QuizAttempt).where(QuizAttempt.quiz_id == quiz.id, QuizAttempt.student_id == student.id)
        .order_by(col(QuizAttempt.submitted_at).desc(), col(QuizAttempt.id).desc())
    ).all()
    return [_attempt_out(a) for a in attempts]
