"""페이지 재구성 백그라운드 작업 (POST /lessons/{id}/generate).

FastAPI BackgroundTasks로 같은 프로세스 이벤트 루프에서 실행된다 (단일 프로세스 전제).
서버가 작업 도중 재시작되면 status가 generating에 머무르므로, 시작 시 recover_stuck_generations()로 정리한다.
"""
import asyncio
import logging
from typing import Any

from sqlmodel import Session, col, select

from app.ai import AIProvider
from app.db import get_engine
from app.models import Lesson, LessonStatus, Page

logger = logging.getLogger(__name__)

_EMPTY_RESULT: dict[str, Any] = {
    "easy_sentences": [],
    "hard_words": [],
    "image_suggestion": {"needed": False, "reason": "", "prompt": ""},
}


async def run_generation(lesson_id: int, provider: AIProvider, concurrency: int = 3) -> None:
    with Session(get_engine()) as session:
        pages = [(p.id, p.page_no, p.source_text) for p in
                 session.exec(select(Page).where(Page.lesson_id == lesson_id).order_by(Page.page_no)).all()]
    total = len(pages)
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def work(page_id: int, page_no: int, text: str) -> tuple[int, int, dict[str, Any] | None]:
        if not text.strip():  # 그림만 있는 페이지 등: 재구성할 글이 없음
            return page_id, page_no, _EMPTY_RESULT
        async with semaphore:
            try:
                return page_id, page_no, await provider.restructure_page(text)
            except Exception:
                logger.exception("페이지 재구성 실패: lesson=%s page=%s", lesson_id, page_no)
                return page_id, page_no, None

    failed: list[int] = []
    try:
        done = 0
        for next_result in asyncio.as_completed([work(*p) for p in pages]):
            page_id, page_no, result = await next_result
            done += 1
            with Session(get_engine()) as session:
                page = session.get(Page, page_id)
                if page is not None:
                    if result is None:
                        failed.append(page_no)
                    else:
                        page.easy_sentences = result["easy_sentences"]
                        page.hard_words = result["hard_words"]
                        page.image_suggestion = result["image_suggestion"]
                    page.approved = False
                    session.add(page)
                lesson = session.get(Lesson, lesson_id)
                if lesson is not None:
                    lesson.progress = min(99, done * 100 // total)  # 100은 완료 처리에서
                    session.add(lesson)
                session.commit()
    finally:
        with Session(get_engine()) as session:
            lesson = session.get(Lesson, lesson_id)
            # ready도 포함: 같은 DB를 쓰는 다른 프로세스가 시작하면서 recover_stuck_generations()로
            # 진행 중인 회차를 먼저 ready로 바꿨을 수 있다. 그래도 끝난 작업의 진행률은 100으로 맞춘다.
            if lesson is not None and lesson.status in (LessonStatus.generating, LessonStatus.ready):
                lesson.status = LessonStatus.ready
                lesson.progress = 100
                session.add(lesson)
                session.commit()
        if failed:
            logger.warning("재구성 완료(실패 페이지 %s). 교사가 직접 수정하거나 다시 생성할 수 있음", sorted(failed))


def recover_stuck_generations() -> int:
    """서버 재시작으로 중단된 generating 회차를 ready로 돌린다 (교사가 다시 생성 가능)."""
    with Session(get_engine()) as session:
        stuck = session.exec(select(Lesson).where(col(Lesson.status) == LessonStatus.generating)).all()
        for lesson in stuck:
            lesson.status = LessonStatus.ready
            session.add(lesson)
        session.commit()
        return len(stuck)
