"""수업 자료 필기 (교사·학생 공통). 자기 필기만 보고 고친다."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlmodel import Session, func, select

from app.db import get_session
from app.deps import get_current_user
from app.models import Annotation, Page, User, utcnow
from app.permissions import get_accessible_lesson
from app.schemas import AnnotationIn, AnnotationList, AnnotationOut

router = APIRouter(tags=["annotations"])

SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/lessons/{lesson_id}/annotations", response_model=AnnotationList, summary="내 필기 (전체 페이지)")
def list_annotations(lesson_id: int, session: SessionDep, user: UserDep) -> AnnotationList:
    get_accessible_lesson(session, lesson_id, user)
    rows = session.exec(
        select(Annotation).where(Annotation.lesson_id == lesson_id, Annotation.user_id == user.id)
        .order_by(Annotation.page_no)
    ).all()
    return AnnotationList(pages=[AnnotationOut(page_no=a.page_no, strokes=a.strokes, updated_at=a.updated_at)
                                 for a in rows])


@router.put("/lessons/{lesson_id}/annotations/{page_no}", response_model=AnnotationOut,
            summary="내 필기 저장 (페이지 전체를 덮어씀, 빈 배열이면 삭제)")
def save_annotation(lesson_id: int, page_no: Annotated[int, Path(ge=1)], body: AnnotationIn,
                    session: SessionDep, user: UserDep) -> AnnotationOut:
    get_accessible_lesson(session, lesson_id, user)
    page_count = session.exec(select(func.count()).select_from(Page).where(Page.lesson_id == lesson_id)).one()
    if page_no > page_count:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "페이지를 찾을 수 없습니다")

    row = session.get(Annotation, (user.id, lesson_id, page_no))
    if not body.strokes:
        if row is not None:
            session.delete(row)
            session.commit()
        return AnnotationOut(page_no=page_no, strokes=[], updated_at=None)

    row = row or Annotation(user_id=user.id, lesson_id=lesson_id, page_no=page_no)
    row.strokes = [s.model_dump() for s in body.strokes]
    row.updated_at = utcnow()
    session.add(row)
    session.commit()
    return AnnotationOut(page_no=page_no, strokes=row.strokes, updated_at=row.updated_at)
