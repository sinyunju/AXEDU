from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, func, select

from app.config import get_settings
from app.db import get_session
from app.deps import get_current_user, require_teacher
from app.models import Lesson, Page, Role, User
from app.pdf import PdfError, remove_files, render_pdf
from app.permissions import get_accessible_lesson, get_owned_course
from app.schemas import LessonDetail, PageOut

router = APIRouter(tags=["lessons"])


def file_url(rel_path: str | None) -> str | None:
    return f"/files/{rel_path}" if rel_path else None


def page_out(page: Page, viewer: User) -> PageOut:
    is_teacher = viewer.role == Role.teacher
    show_easy = is_teacher or page.approved
    return PageOut(
        page_no=page.page_no,
        image_url=file_url(page.image_path),
        easy_sentences=page.easy_sentences if show_easy else [],
        hard_words=page.hard_words if show_easy else [],
        generated_image_url=file_url(page.generated_image_path) if show_easy else None,
        approved=page.approved,
        source_text=page.source_text if is_teacher else None,
        image_suggestion=page.image_suggestion if is_teacher else None,
    )


def lesson_detail(session: Session, lesson: Lesson, viewer: User) -> LessonDetail:
    pages = session.exec(select(Page).where(Page.lesson_id == lesson.id).order_by(Page.page_no)).all()
    return LessonDetail(
        **lesson.model_dump(),
        page_count=len(pages),
        pages=[page_out(p, viewer) for p in pages],
    )


def _session_no_taken(session: Session, course_id: int, session_no: int) -> bool:
    return session.exec(
        select(func.count()).select_from(Lesson).where(Lesson.course_id == course_id, Lesson.session_no == session_no)
    ).one() > 0


@router.post(
    "/courses/{course_id}/lessons",
    response_model=LessonDetail,
    status_code=status.HTTP_201_CREATED,
    summary="회차 생성 + PDF 업로드 (교사)",
    description="PDF를 페이지별로 나눠 텍스트를 추출하고 PNG로 렌더링한다. 재구성은 POST /lessons/{id}/generate 로 따로 시작.",
    responses={400: {"description": "PDF가 아니거나 읽을 수 없음"}, 409: {"description": "회차 번호 중복"},
               413: {"description": "파일이 너무 큼"}},
)
def upload_lesson(
    course_id: int,
    file: UploadFile = File(description="수업 자료 PDF"),
    session_no: int = Form(ge=1, description="회차 번호"),
    title: str = Form(min_length=1, max_length=200),
    class_date: date | None = Form(None, description="수업 날짜 (YYYY-MM-DD)"),
    session: Session = Depends(get_session),
    teacher: User = Depends(require_teacher),
) -> LessonDetail:
    settings = get_settings()
    course = get_owned_course(session, course_id, teacher)
    if _session_no_taken(session, course.id, session_no):  # 렌더링 전에 빠르게 거절
        raise HTTPException(status.HTTP_409_CONFLICT, f"{session_no}회차가 이미 있습니다")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"파일은 {settings.max_upload_mb}MB 이하만 올릴 수 있습니다")

    try:
        rendered = render_pdf(data, settings.storage_dir, max_pages=settings.max_pdf_pages, zoom=settings.pdf_render_zoom)
    except PdfError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    lesson = Lesson(course_id=course.id, session_no=session_no, title=title, class_date=class_date)
    try:
        session.add(lesson)
        session.flush()
        session.add_all(
            Page(lesson_id=lesson.id, page_no=r.page_no, image_path=r.image_path, source_text=r.source_text)
            for r in rendered
        )
        session.commit()
    except IntegrityError:  # 동시 업로드로 회차 번호가 겹친 경우
        session.rollback()
        remove_files([settings.storage_dir / r.image_path for r in rendered])
        raise HTTPException(status.HTTP_409_CONFLICT, f"{session_no}회차가 이미 있습니다")
    except Exception:
        session.rollback()
        remove_files([settings.storage_dir / r.image_path for r in rendered])
        raise
    session.refresh(lesson)
    return lesson_detail(session, lesson, teacher)


@router.get(
    "/lessons/{lesson_id}",
    response_model=LessonDetail,
    summary="회차 상세 (교사: 전체 / 학생: 승인된 회차·내용만)",
)
def get_lesson(
    lesson_id: int, session: Session = Depends(get_session), user: User = Depends(get_current_user)
) -> LessonDetail:
    lesson = get_accessible_lesson(session, lesson_id, user)
    return lesson_detail(session, lesson, user)
