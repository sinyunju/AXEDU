"""리소스 접근 권한 헬퍼. 없는 리소스는 404, 권한이 없으면 403."""
from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models import Course, Enrollment, LessonStatus, Role, User

# 학생에게 공개되는 회차 상태 (교사 승인 이후)
STUDENT_VISIBLE_STATUSES = (LessonStatus.approved, LessonStatus.live, LessonStatus.ended)


def is_enrolled(session: Session, course_id: int, student_id: int) -> bool:
    return (
        session.exec(
            select(Enrollment.id).where(Enrollment.course_id == course_id, Enrollment.student_id == student_id)
        ).first()
        is not None
    )


def get_course_or_404(session: Session, course_id: int) -> Course:
    course = session.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "과목을 찾을 수 없습니다")
    return course


def get_accessible_course(session: Session, course_id: int, user: User) -> Course:
    """교사: 자기 과목 / 학생: 등록한 과목."""
    course = get_course_or_404(session, course_id)
    if user.role == Role.teacher:
        if course.teacher_id != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "내 과목이 아닙니다")
    elif not is_enrolled(session, course.id, user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "등록하지 않은 과목입니다")
    return course


def get_owned_course(session: Session, course_id: int, teacher: User) -> Course:
    """교사 전용 API용. 호출 전에 require_teacher로 역할을 확인했다고 가정."""
    course = get_course_or_404(session, course_id)
    if course.teacher_id != teacher.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "내 과목이 아닙니다")
    return course
