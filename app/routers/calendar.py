"""메인 화면 캘린더: 내 수업 회차 일정 (+ 나중에 슈퍼스쿨 학사 일정을 합칠 자리)."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, col, select

from app.db import get_session
from app.deps import get_current_user
from app.models import Course, Enrollment, Lesson, Role, User
from app.permissions import STUDENT_VISIBLE_STATUSES
from app.schemas import CalendarEvent, CalendarOut

router = APIRouter(tags=["calendar"])

MAX_RANGE_DAYS = 400


def _parse_day(value: str, name: str) -> date:
    """YYYY-MM-DD 또는 ISO 날짜시간(2026-11-01T00:00:00Z 등) → 날짜."""
    try:
        return datetime.fromisoformat(value).date() if "T" in value else date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{name}는 ISO 날짜(YYYY-MM-DD)여야 합니다")


@router.get("/calendar", response_model=CalendarOut, summary="내 일정 (수업 회차)",
            description="from~to(양 끝 포함)에 수업 날짜(class_date)가 있는 회차. 교사: 내 과목 전체 / "
                        "학생: 등록 과목의 승인된(approved 이상) 회차만. 수업 날짜에 시각이 없어 종일 일정으로 준다.")
def calendar(
    from_: str = Query(alias="from", examples=["2026-11-01"]),
    to: str = Query(examples=["2026-11-30"]),
    session: Session = Depends(get_session), user: User = Depends(get_current_user),
) -> CalendarOut:
    start, end = _parse_day(from_, "from"), _parse_day(to, "to")
    if end < start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "to는 from보다 앞설 수 없습니다")
    if (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"한 번에 {MAX_RANGE_DAYS}일까지 조회할 수 있습니다")

    stmt = (select(Lesson, Course).join(Course, Course.id == Lesson.course_id)
            .where(col(Lesson.class_date).is_not(None), Lesson.class_date >= start, Lesson.class_date <= end))
    if user.role == Role.teacher:
        stmt = stmt.where(Course.teacher_id == user.id)
    else:
        stmt = (stmt.join(Enrollment, Enrollment.course_id == Course.id)
                .where(Enrollment.student_id == user.id, col(Lesson.status).in_(STUDENT_VISIBLE_STATUSES)))
    rows = session.exec(stmt.order_by(Lesson.class_date, Course.name, Lesson.session_no)).all()
    events = [
        CalendarEvent(id=f"lesson-{lesson.id}", title=f"{course.name} {lesson.session_no}회차 · {lesson.title}",
                      start=lesson.class_date.isoformat(), all_day=True, source="lesson", lesson_id=lesson.id,
                      lesson_status=lesson.status, course_name=course.name)
        for lesson, course in rows
    ]
    return CalendarOut(superschool_linked=False, events=events)
