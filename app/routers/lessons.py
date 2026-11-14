from datetime import date

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, func, select

from app.ai import AIError, AIProvider, ImageProvider, get_ai_provider, get_image_provider
from app.ai.base import image_extension
from app.config import get_settings
from app.db import get_session
from app.deps import get_current_user, require_teacher
from app.models import Lesson, LessonStatus, Page, PageLive, Role, User
from app.pdf import PdfError, remove_files, render_pdf
from app.permissions import get_accessible_lesson, get_owned_course, get_owned_lesson
from app.schemas import (ImageRequest, LessonDetail, LessonInfoUpdate, LessonOut, PageOut, PageUpdate, PageView,
                         TermExplainOut, TermExplainRequest)
from app.services.generation import run_generation
from app.services.live import normalize_captions
from app.storage import GENERATED_SUBDIR, delete_file, save_file

logger = logging.getLogger(__name__)
router = APIRouter(tags=["lessons"])

# 승인 이후(approved/live/ended)에는 재생성 불가
_REGENERATABLE = (LessonStatus.uploaded, LessonStatus.ready)


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


def _pages(session: Session, lesson_id: int) -> list[Page]:
    return list(session.exec(select(Page).where(Page.lesson_id == lesson_id).order_by(Page.page_no)).all())


def lesson_out(session: Session, lesson: Lesson) -> LessonOut:
    count = session.exec(select(func.count()).select_from(Page).where(Page.lesson_id == lesson.id)).one()
    return LessonOut(**lesson.model_dump(), page_count=count)


def lesson_detail(session: Session, lesson: Lesson, viewer: User) -> LessonDetail:
    pages = _pages(session, lesson.id)
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


# ---------- 5단계: 재구성 / 수정 / 이미지 / 승인 (교사) ----------
def _get_page(session: Session, lesson: Lesson, page_no: int) -> Page:
    page = session.exec(select(Page).where(Page.lesson_id == lesson.id, Page.page_no == page_no)).first()
    if page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "페이지를 찾을 수 없습니다")
    return page


def _ensure_not_generating(lesson: Lesson) -> None:
    if lesson.status == LessonStatus.generating:
        raise HTTPException(status.HTTP_409_CONFLICT, "재구성 작업 중입니다. 끝난 뒤 다시 시도해 주세요")


@router.post(
    "/lessons/{lesson_id}/generate",
    response_model=LessonOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="페이지별 쉬운 문장 재구성 시작 (교사)",
    description="백그라운드로 실행된다. 진행률은 GET /lessons/{id} 의 progress(0~100)와 status(generating → ready)로 확인.",
    responses={409: {"description": "이미 진행 중이거나 승인 이후 회차"}},
)
def generate_lesson(
    lesson_id: int,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    teacher: User = Depends(require_teacher),
    provider: AIProvider = Depends(get_ai_provider),
) -> LessonOut:
    lesson = get_owned_lesson(session, lesson_id, teacher)
    _ensure_not_generating(lesson)
    if lesson.status not in _REGENERATABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, "승인된 회차는 다시 생성할 수 없습니다")
    lesson.status = LessonStatus.generating
    lesson.progress = 0
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
    background_tasks.add_task(run_generation, lesson.id, provider, get_settings().generate_concurrency)
    return lesson_out(session, lesson)


@router.patch("/lessons/{lesson_id}", response_model=LessonOut, summary="회차 정보 수정 (교사)",
              description="회차 번호·제목·수업 날짜 중 보낸 것만 바꾼다. class_date에 null을 보내면 날짜를 지운다. "
                          "수업 자료(PDF)와 페이지 내용은 바뀌지 않으며, 수업 중이어도 바꿀 수 있다.",
              responses={409: {"description": "같은 과목에 그 회차 번호가 이미 있음"}})
def update_lesson(
    lesson_id: int, body: LessonInfoUpdate,
    session: Session = Depends(get_session), teacher: User = Depends(require_teacher),
) -> LessonOut:
    lesson = get_owned_lesson(session, lesson_id, teacher)
    if body.session_no is not None and body.session_no != lesson.session_no:
        if _session_no_taken(session, lesson.course_id, body.session_no):
            raise HTTPException(status.HTTP_409_CONFLICT, f"{body.session_no}회차가 이미 있습니다")
        lesson.session_no = body.session_no
    if body.title is not None:
        lesson.title = body.title
    if "class_date" in body.model_fields_set:
        lesson.class_date = body.class_date
    session.add(lesson)
    try:
        session.commit()
    except IntegrityError:  # 동시 수정으로 회차 번호가 겹친 경우
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"{body.session_no}회차가 이미 있습니다")
    session.refresh(lesson)
    return lesson_out(session, lesson)


@router.put("/lessons/{lesson_id}/pages/{page_no}", response_model=PageOut, summary="쉬운 문장·어려운 낱말 수정 (교사)")
def update_page(
    lesson_id: int, page_no: int, body: PageUpdate,
    session: Session = Depends(get_session), teacher: User = Depends(require_teacher),
) -> PageOut:
    lesson = get_owned_lesson(session, lesson_id, teacher)
    _ensure_not_generating(lesson)
    page = _get_page(session, lesson, page_no)
    if body.easy_sentences is None and body.hard_words is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "easy_sentences 또는 hard_words 중 하나는 보내야 합니다")
    if body.easy_sentences is not None:
        page.easy_sentences = body.easy_sentences
    if body.hard_words is not None:
        page.hard_words = [w.model_dump() for w in body.hard_words]
    session.add(page)
    session.commit()
    session.refresh(page)
    return page_out(page, teacher)


@router.post(
    "/lessons/{lesson_id}/pages/{page_no}/terms/explain", response_model=TermExplainOut,
    summary="낱말 뜻 AI로 채우기 (교사)",
    description="그 페이지 글을 문맥으로 낱말의 쉬운 뜻을 만들어 돌려준다. 저장하지 않으므로, 교사가 확인한 뒤 "
                "`PUT /lessons/{id}/pages/{n}`의 hard_words로 저장한다.",
)
async def explain_term(
    lesson_id: int, page_no: int, body: TermExplainRequest,
    session: Session = Depends(get_session), teacher: User = Depends(require_teacher),
    provider: AIProvider = Depends(get_ai_provider),
) -> TermExplainOut:
    lesson = get_owned_lesson(session, lesson_id, teacher)
    page = _get_page(session, lesson, page_no)
    try:
        result = await provider.explain_term(page.source_text, body.word)
    except AIError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "지금은 뜻을 만들 수 없어요. 잠시 후 다시 시도해 주세요")
    return TermExplainOut(word=body.word, meaning=result["meaning"])


@router.post(
    "/lessons/{lesson_id}/pages/{page_no}/image",
    response_model=PageOut,
    summary="페이지 이미지 생성 (교사)",
    description="prompt를 비우면 AI 제안(image_suggestion.prompt)을 사용. 기존 생성 이미지는 교체된다. "
                "MOCK_IMAGE=true면 실제 호출 없이 자리표시 이미지를 만든다.",
    responses={400: {"description": "사용할 프롬프트가 없음"}, 502: {"description": "이미지 생성 API 실패"}},
)
async def generate_page_image(
    lesson_id: int, page_no: int, body: ImageRequest | None = None,
    session: Session = Depends(get_session), teacher: User = Depends(require_teacher),
    image_provider: ImageProvider = Depends(get_image_provider),
    provider: AIProvider = Depends(get_ai_provider),
) -> PageOut:
    lesson = get_owned_lesson(session, lesson_id, teacher)
    _ensure_not_generating(lesson)
    page = _get_page(session, lesson, page_no)

    custom_prompt = (body.prompt or "").strip() if body else ""
    suggestion = page.image_suggestion or {}
    prompt = custom_prompt or (suggestion.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "AI 제안 프롬프트가 없습니다. prompt를 직접 입력해 주세요")

    try:
        english = await provider.image_prompt(prompt)  # 이미지 모델은 한국어 프롬프트에 이미지를 잘 안 돌려줌
    except AIError as e:
        logger.warning("이미지 프롬프트 번역 실패, 원문으로 시도: %s", e)
        english = prompt
    try:
        image = await image_provider.generate_image(english)
    except AIError as e:
        logger.warning("이미지 생성 실패 lesson=%s page=%s: %s", lesson_id, page_no, e)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "이미지를 만들지 못했습니다. 잠시 후 다시 시도해 주세요")
    ext = image_extension(image) or "png"

    old_path = page.generated_image_path
    page.generated_image_path = save_file(GENERATED_SUBDIR, image, ext)
    page.image_suggestion = {
        "needed": True,
        "reason": suggestion.get("reason") or ("교사가 직접 요청" if custom_prompt else ""),
        "prompt": prompt,
    }
    session.add(page)
    session.commit()
    session.refresh(page)
    delete_file(old_path)
    return page_out(page, teacher)


@router.delete("/lessons/{lesson_id}/pages/{page_no}/image", response_model=PageOut, summary="이미지·이미지 제안 삭제 (교사)")
def delete_page_image(
    lesson_id: int, page_no: int,
    session: Session = Depends(get_session), teacher: User = Depends(require_teacher),
) -> PageOut:
    lesson = get_owned_lesson(session, lesson_id, teacher)
    _ensure_not_generating(lesson)
    page = _get_page(session, lesson, page_no)
    old_path = page.generated_image_path
    page.generated_image_path = None
    page.image_suggestion = None
    session.add(page)
    session.commit()
    session.refresh(page)
    delete_file(old_path)
    return page_out(page, teacher)


@router.post(
    "/lessons/{lesson_id}/approve",
    response_model=LessonDetail,
    summary="회차 승인 → 학생에게 공개 (교사)",
    responses={409: {"description": "재구성 전/중이거나 이미 수업이 시작된 회차"}},
)
def approve_lesson(
    lesson_id: int, session: Session = Depends(get_session), teacher: User = Depends(require_teacher),
) -> LessonDetail:
    lesson = get_owned_lesson(session, lesson_id, teacher)
    if lesson.status in (LessonStatus.uploaded, LessonStatus.generating):
        raise HTTPException(status.HTTP_409_CONFLICT, "재구성을 마친 뒤 승인할 수 있습니다")
    if lesson.status in (LessonStatus.live, LessonStatus.ended):
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 수업이 시작된 회차입니다")
    for page in _pages(session, lesson.id):
        page.approved = True
        session.add(page)
    lesson.status = LessonStatus.approved
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
    return lesson_detail(session, lesson, teacher)


# ---------- 6단계: 수업 시작/종료, 학생 페이지 조회 ----------
@router.post(
    "/lessons/{lesson_id}/start",
    response_model=LessonOut,
    summary="실시간 수업 시작 (교사)",
    description="approved → live (선생님 페이지는 1쪽부터). ended → live는 수업 재개로 보고 페이지를 유지한다. "
                "이미 live면 그대로 반환. WebSocket으로 lesson_started를 보낸다.",
    responses={409: {"description": "승인 전 회차"}},
)
async def start_lesson(
    lesson_id: int, request: Request,
    session: Session = Depends(get_session), teacher: User = Depends(require_teacher),
) -> LessonOut:
    lesson = get_owned_lesson(session, lesson_id, teacher)
    if lesson.status == LessonStatus.live:
        return lesson_out(session, lesson)
    if lesson.status not in (LessonStatus.approved, LessonStatus.ended):
        raise HTTPException(status.HTTP_409_CONFLICT, "승인한 회차만 수업을 시작할 수 있습니다")
    if lesson.status == LessonStatus.approved:
        lesson.current_page = 1
    lesson.status = LessonStatus.live
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
    await request.app.state.live.connections.broadcast(
        lesson.id, {"type": "lesson_started", "page_no": lesson.current_page})
    return lesson_out(session, lesson)


@router.post(
    "/lessons/{lesson_id}/end",
    response_model=LessonOut,
    summary="수업 종료 (교사)",
    description="live → ended. 이미 ended면 그대로 반환. WebSocket으로 lesson_ended를 보낸다.",
    responses={409: {"description": "진행 중인 수업이 아님"}},
)
async def end_lesson(
    lesson_id: int, request: Request,
    session: Session = Depends(get_session), teacher: User = Depends(require_teacher),
) -> LessonOut:
    lesson = get_owned_lesson(session, lesson_id, teacher)
    if lesson.status == LessonStatus.ended:
        return lesson_out(session, lesson)
    if lesson.status != LessonStatus.live:
        raise HTTPException(status.HTTP_409_CONFLICT, "진행 중인 수업이 아닙니다")
    lesson.status = LessonStatus.ended
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
    hub = request.app.state.live
    hub.captioner.flush_lesson(lesson.id)  # 남은 발화는 마지막으로 자막 처리 (결과는 page_update로 뒤따라옴)
    await hub.connections.broadcast(lesson.id, {"type": "lesson_ended"})
    return lesson_out(session, lesson)


@router.get(
    "/lessons/{lesson_id}/pages/{page_no}",
    response_model=PageView,
    summary="페이지 보기 (학생 화면용, 교사도 사용 가능)",
    description="원본 이미지, 쉬운 문장, 어려운 낱말, 생성 이미지, 지금까지의 쉬운 자막, 선생님의 현재 페이지. "
                "학생은 승인된 회차만 조회 가능.",
)
def get_page_view(
    lesson_id: int, page_no: int, session: Session = Depends(get_session), user: User = Depends(get_current_user),
) -> PageView:
    lesson = get_accessible_lesson(session, lesson_id, user)
    page = _get_page(session, lesson, page_no)
    out = page_out(page, user)  # 학생에게는 승인된 페이지 내용만
    live = session.get(PageLive, (lesson.id, page_no))
    page_count = session.exec(select(func.count()).select_from(Page).where(Page.lesson_id == lesson.id)).one()
    return PageView(
        lesson_id=lesson.id,
        page_no=page_no,
        page_count=page_count,
        lesson_status=lesson.status,
        teacher_page=lesson.current_page,
        image_url=out.image_url,
        easy_sentences=out.easy_sentences,
        hard_words=out.hard_words,
        generated_image_url=out.generated_image_url,
        easy_transcript=normalize_captions(live.easy_transcript) if live else [],
        transcript_hard_words=live.hard_words if live else [],
        transcript_updated_at=live.updated_at if live else None,
    )
