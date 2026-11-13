"""요청/응답 Pydantic 스키마 (/docs 프론트 연동 기준)."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models import LessonStatus, Role


class SignupRequest(BaseModel):
    login_id: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$", examples=["teacher1"])
    password: str = Field(min_length=4, examples=["pass1234"])
    name: str = Field(min_length=1, max_length=50, examples=["김선생"])
    role: Role = Field(examples=["teacher"])

    @field_validator("password")
    @classmethod
    def _bcrypt_limit(cls, v: str) -> str:
        if len(v.encode()) > 72:
            raise ValueError("비밀번호는 72바이트 이하여야 합니다")
        return v


class LoginRequest(BaseModel):
    login_id: str = Field(examples=["teacher1"])
    password: str = Field(examples=["pass1234"])


class UserBrief(BaseModel):
    id: int
    name: str
    role: Role


class UserOut(UserBrief):
    login_id: str
    created_at: datetime


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserBrief


# ---------- 과목 ----------
class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, examples=["과학"])
    description: str = Field(default="", max_length=1000, examples=["2학기 과학 수업"])


class CourseOut(BaseModel):
    id: int
    name: str
    description: str
    teacher_id: int
    teacher_name: str
    invite_code: str | None = Field(None, description="교사에게만 제공. 학생에게는 null")
    created_at: datetime


class LessonBrief(BaseModel):
    id: int
    session_no: int
    title: str
    class_date: date | None
    status: LessonStatus
    progress: int


class CourseDetail(CourseOut):
    lessons: list[LessonBrief] = Field(description="회차 번호 순. 학생에게는 승인된(approved/live/ended) 회차만")


class CourseStudent(BaseModel):
    id: int
    login_id: str
    name: str
    joined_at: datetime


class JoinRequest(BaseModel):
    invite_code: str = Field(min_length=6, max_length=6, examples=["DEMO01"], description="대소문자 구분 없음")


class JoinResponse(BaseModel):
    course: CourseOut
    joined_at: datetime


# ---------- 회차 / 페이지 ----------
class HardWord(BaseModel):
    word: str
    meaning: str


class ImageSuggestion(BaseModel):
    needed: bool
    reason: str = ""
    prompt: str = ""


class PageOut(BaseModel):
    page_no: int
    image_url: str = Field(description="원본 페이지 PNG (/files/...)")
    easy_sentences: list[str] = Field(description="학생에게는 승인된 페이지만 채워짐")
    hard_words: list[HardWord]
    generated_image_url: str | None
    approved: bool
    source_text: str | None = Field(None, description="교사에게만 제공")
    image_suggestion: ImageSuggestion | None = Field(None, description="교사에게만 제공")


class LessonOut(BaseModel):
    id: int
    course_id: int
    session_no: int
    title: str
    class_date: date | None
    status: LessonStatus
    progress: int = Field(description="페이지 재구성 진행률 0~100")
    current_page: int
    page_count: int
    created_at: datetime


class LessonDetail(LessonOut):
    pages: list[PageOut]


# ---------- 5단계: 재구성 / 수정 / 이미지 ----------
class PageUpdate(BaseModel):
    easy_sentences: list[str] | None = Field(None, examples=[["식물은 햇빛으로 양분을 만들어요."]])
    hard_words: list[HardWord] | None = None

    @field_validator("easy_sentences")
    @classmethod
    def _clean_sentences(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        cleaned = [s.strip() for s in v if s.strip()]
        if any(len(s) > 500 for s in cleaned):
            raise ValueError("문장은 500자 이하여야 합니다")
        return cleaned


class ImageRequest(BaseModel):
    prompt: str | None = Field(
        None, max_length=1000, description="비우면 AI가 제안한 image_suggestion.prompt를 사용",
        examples=["잎에 햇빛이 비치고 뿌리로 물이 올라가는 모습"],
    )


# ---------- 6단계: 학생 페이지 조회 ----------
class CaptionItem(BaseModel):
    text: str
    type: Literal["content", "flow", "notice"] = Field(
        description="content: 수업 내용 / flow: 수업 흐름 안내(\"지금부터 정리해요\") / notice: 과제·준비물 안내")

class PageView(BaseModel):
    """학생 화면의 한 페이지. 학생은 자유롭게 페이지를 이동하고, teacher_page로 선생님 위치만 안다."""

    lesson_id: int
    page_no: int
    page_count: int
    lesson_status: LessonStatus
    teacher_page: int = Field(description="선생님이 지금 보고 있는 페이지 (Lesson.current_page)")
    image_url: str
    easy_sentences: list[str]
    hard_words: list[HardWord]
    generated_image_url: str | None
    easy_transcript: list[CaptionItem] = Field(description="이 페이지에서 지금까지 나온 선생님 말씀의 쉬운 자막")
    transcript_hard_words: list[HardWord] = Field(description="실시간 자막에서 나온 어려운 낱말")
    transcript_updated_at: datetime | None


# ---------- 8단계: 퀴즈 ----------
class QuizQuestionOut(BaseModel):
    id: int
    type: str = Field(description='"ox" | "choice"')
    question: str
    choices: list[str] = Field(description='ox는 ["O", "X"], choice는 보기 3개')
    page_no: int | None = Field(description="근거 페이지")
    answer: str | None = Field(None, description="교사에게만 제공 (학생은 제출 후 결과에서 확인)")
    explanation: str | None = Field(None, description="교사에게만 제공")


class QuizOut(BaseModel):
    id: int
    lesson_id: int
    questions: list[QuizQuestionOut]


class AttemptAnswer(BaseModel):
    question_id: int
    answer: str = Field(max_length=200, examples=["O"], description='ox는 "O"/"X", choice는 보기 글 그대로')


class AttemptCreate(BaseModel):
    answers: list[AttemptAnswer] = Field(description="답하지 않은 문항은 오답 처리")


class AttemptResultItem(BaseModel):
    question_id: int
    answer: str | None
    correct: bool
    correct_answer: str
    explanation: str
    page_no: int | None


class AttemptOut(BaseModel):
    id: int
    quiz_id: int
    score: int
    total: int
    submitted_at: datetime
    results: list[AttemptResultItem]


# ---------- 9단계: 챗봇 ----------
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500, examples=["광합성은 어디에서 일어나요?"])

    @field_validator("message")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("질문을 입력해 주세요")
        return v.strip()


class ChatMessageOut(BaseModel):
    id: int
    role: str = Field(description='"user" | "assistant"')
    content: str
    related_page: int | None = Field(description="답변의 근거 페이지 (assistant만)")
    created_at: datetime


class ChatExchange(BaseModel):
    question: ChatMessageOut
    answer: ChatMessageOut
