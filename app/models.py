"""DB 모델 (CLAUDE.md 3절)."""
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class Role(StrEnum):
    teacher = "teacher"
    student = "student"


class LessonStatus(StrEnum):
    uploaded = "uploaded"
    generating = "generating"
    ready = "ready"
    approved = "approved"
    live = "live"
    ended = "ended"


class ChatRole(StrEnum):
    user = "user"
    assistant = "assistant"


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    login_id: str = Field(index=True, unique=True)
    password_hash: str
    name: str
    role: Role
    avatar_path: str | None = None  # 프로필 사진 (storage_dir 기준 상대 경로)
    created_at: datetime = Field(default_factory=utcnow)


class Course(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    teacher_id: int = Field(foreign_key="user.id", index=True)
    name: str
    description: str = ""
    invite_code: str = Field(index=True, unique=True, max_length=6)
    created_at: datetime = Field(default_factory=utcnow)


class Enrollment(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("course_id", "student_id"),)

    id: int | None = Field(default=None, primary_key=True)
    course_id: int = Field(foreign_key="course.id", index=True)
    student_id: int = Field(foreign_key="user.id", index=True)
    joined_at: datetime = Field(default_factory=utcnow)


class Lesson(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("course_id", "session_no"),)

    id: int | None = Field(default=None, primary_key=True)
    course_id: int = Field(foreign_key="course.id", index=True)
    session_no: int
    title: str
    class_date: date | None = None
    status: LessonStatus = LessonStatus.uploaded
    progress: int = 0
    current_page: int = 1
    created_at: datetime = Field(default_factory=utcnow)


class Page(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("lesson_id", "page_no"),)

    id: int | None = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="lesson.id", index=True)
    page_no: int
    image_path: str
    source_text: str = ""
    easy_sentences: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    hard_words: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    image_suggestion: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    generated_image_path: str | None = None
    approved: bool = False


class Transcript(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="lesson.id", index=True)
    page_no: int
    text: str
    created_at: datetime = Field(default_factory=utcnow)


class PageLive(SQLModel, table=True):
    lesson_id: int = Field(foreign_key="lesson.id", primary_key=True)
    page_no: int = Field(primary_key=True)
    # [{text, type: content|flow|notice}] (예전 데이터는 문자열 목록일 수 있음 → normalize_captions)
    easy_transcript: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    # 명세 v2에 추가: 실시간 자막에서 나온 어려운 낱말 (재접속 시 복원용)
    hard_words: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    # 여기까지(Transcript.id) 자막으로 만들었음. 다음 호출은 이보다 뒤의 발화만 LLM에 넘긴다
    captioned_upto: int = 0
    updated_at: datetime = Field(default_factory=utcnow)


class Quiz(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="lesson.id", unique=True)
    questions: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))


class QuizAttempt(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    quiz_id: int = Field(foreign_key="quiz.id", index=True)
    student_id: int = Field(foreign_key="user.id", index=True)
    answers: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    score: int = 0
    submitted_at: datetime = Field(default_factory=utcnow)


class ChatMessage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="lesson.id", index=True)
    student_id: int = Field(foreign_key="user.id", index=True)
    role: ChatRole
    content: str
    related_page: int | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Annotation(SQLModel, table=True):
    """수업 자료 위 필기. 사용자·회차·페이지마다 하나 (본인만 보고 고친다).

    strokes: [{"tool": "pen"|"highlighter", "color": "#rrggbb", "width": 0.004,
               "points": [[x, y], ...]}]  x·y·width는 페이지 너비·높이 기준 0~1 비율
    """
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    lesson_id: int = Field(foreign_key="lesson.id", primary_key=True)
    page_no: int = Field(primary_key=True)
    strokes: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=utcnow)
