"""회차의 수업 내용 (퀴즈·챗봇의 근거): 승인된 페이지 + 그 페이지의 교사 발화."""
from typing import Any

from sqlmodel import Session, select

from app.models import Page, Transcript


def lesson_content(session: Session, lesson_id: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """승인된 페이지 내용 + 교사 발화."""
    pages = session.exec(
        select(Page).where(Page.lesson_id == lesson_id, Page.approved == True).order_by(Page.page_no)  # noqa: E712
    ).all()
    transcripts = session.exec(
        select(Transcript).where(Transcript.lesson_id == lesson_id).order_by(Transcript.id)
    ).all()
    page_dicts = [
        {"page_no": p.page_no, "easy_sentences": p.easy_sentences, "hard_words": p.hard_words,
         "source_text": p.source_text}
        for p in pages
    ]
    approved = {p.page_no for p in pages}
    talk = [{"page_no": t.page_no, "text": t.text} for t in transcripts if t.page_no in approved]
    return page_dicts, talk
