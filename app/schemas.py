"""요청/응답 Pydantic 스키마 (/docs 프론트 연동 기준)."""
from datetime import date, datetime

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
