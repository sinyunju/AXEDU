"""리소스 접근 권한 헬퍼. 없는 리소스는 404, 권한이 없으면 403."""
from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models import Course, Enrollment, Lesson, LessonStatus, Role, User

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


def get_lesson_or_404(session: Session, lesson_id: int) -> Lesson:
    lesson = session.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "수업 회차를 찾을 수 없습니다")
    return lesson


def get_accessible_lesson(session: Session, lesson_id: int, user: User) -> Lesson:
    """교사: 자기 과목의 회차 / 학생: 등록 과목의 승인된 회차.

    학생에게 아직 승인되지 않은 회차는 존재 자체를 숨기기 위해 404로 응답한다.
    """
    lesson = get_lesson_or_404(session, lesson_id)
    get_accessible_course(session, lesson.course_id, user)
    if user.role == Role.student and lesson.status not in STUDENT_VISIBLE_STATUSES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "수업 회차를 찾을 수 없습니다")
    return lesson


def get_owned_lesson(session: Session, lesson_id: int, teacher: User) -> Lesson:
    lesson = get_lesson_or_404(session, lesson_id)
    get_owned_course(session, lesson.course_id, teacher)
    return lesson
