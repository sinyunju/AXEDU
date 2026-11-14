from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, func, select

from app.db import get_session
from app.deps import get_current_user, require_student, require_teacher
from app.models import Course, Enrollment, Lesson, Role, User
from app.permissions import STUDENT_VISIBLE_STATUSES, get_accessible_course, get_owned_course
from app.schemas import (CourseCreate, CourseDetail, CourseOut, CourseStudent, CourseUpdate, JoinRequest, JoinResponse,
                         LessonBrief)
from app.security import generate_invite_code

router = APIRouter(prefix="/courses", tags=["courses"])

_INVITE_CODE_ATTEMPTS = 10


def _lesson_count(session: Session, course_id: int, viewer: User) -> int:
    stmt = select(func.count()).select_from(Lesson).where(Lesson.course_id == course_id)
    if viewer.role == Role.student:
        stmt = stmt.where(col(Lesson.status).in_(STUDENT_VISIBLE_STATUSES))
    return session.exec(stmt).one()


def _course_out(session: Session, course: Course, viewer: User) -> CourseOut:
    teacher = session.get(User, course.teacher_id)
    return CourseOut(
        id=course.id,
        name=course.name,
        description=course.description,
        teacher_id=course.teacher_id,
        teacher_name=teacher.name if teacher else "",
        invite_code=course.invite_code if viewer.role == Role.teacher else None,
        lesson_count=_lesson_count(session, course.id, viewer),
        created_at=course.created_at,
    )


@router.post("", response_model=CourseOut, status_code=status.HTTP_201_CREATED, summary="과목 생성 (교사)")
def create_course(
    body: CourseCreate, session: Session = Depends(get_session), teacher: User = Depends(require_teacher)
) -> CourseOut:
    for _ in range(_INVITE_CODE_ATTEMPTS):
        course = Course(teacher_id=teacher.id, name=body.name, description=body.description,
                        invite_code=generate_invite_code())
        session.add(course)
        try:
            session.commit()
        except IntegrityError:  # 초대 코드 충돌 → 새 코드로 재시도
            session.rollback()
            continue
        session.refresh(course)
        return _course_out(session, course, teacher)
    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "초대 코드를 만들지 못했습니다. 다시 시도해 주세요")


@router.patch("/{course_id}", response_model=CourseOut, summary="과목 이름·설명 수정 (교사)",
              description="보낸 필드만 바꾼다. 초대 코드는 그대로.")
def update_course(
    course_id: int, body: CourseUpdate,
    session: Session = Depends(get_session), teacher: User = Depends(require_teacher),
) -> CourseOut:
    course = get_owned_course(session, course_id, teacher)
    if body.name is not None:
        course.name = body.name
    if body.description is not None:
        course.description = body.description
    session.add(course)
    session.commit()
    session.refresh(course)
    return _course_out(session, course, teacher)


@router.get("", response_model=list[CourseOut], summary="내 과목 목록 (교사: 만든 과목 / 학생: 등록한 과목)")
def list_courses(session: Session = Depends(get_session), user: User = Depends(get_current_user)) -> list[CourseOut]:
    if user.role == Role.teacher:
        stmt = select(Course).where(Course.teacher_id == user.id)
    else:
        stmt = select(Course).join(Enrollment, Enrollment.course_id == Course.id).where(Enrollment.student_id == user.id)
    courses = session.exec(stmt.order_by(col(Course.created_at).desc(), col(Course.id).desc())).all()
    return [_course_out(session, c, user) for c in courses]


@router.post("/join", response_model=JoinResponse, status_code=status.HTTP_201_CREATED,
             summary="초대 코드로 과목 등록 (학생)")
def join_course(
    body: JoinRequest, session: Session = Depends(get_session), student: User = Depends(require_student)
) -> JoinResponse:
    code = body.invite_code.strip().upper()
    course = session.exec(select(Course).where(Course.invite_code == code)).first()
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "초대 코드에 맞는 과목이 없습니다")
    enrollment = Enrollment(course_id=course.id, student_id=student.id)
    session.add(enrollment)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 등록한 과목입니다")
    session.refresh(enrollment)
    return JoinResponse(course=_course_out(session, course, student), joined_at=enrollment.joined_at)


@router.get("/{course_id}", response_model=CourseDetail, summary="과목 정보 + 회차 목록")
def get_course(
    course_id: int, session: Session = Depends(get_session), user: User = Depends(get_current_user)
) -> CourseDetail:
    course = get_accessible_course(session, course_id, user)
    stmt = select(Lesson).where(Lesson.course_id == course.id)
    if user.role == Role.student:
        stmt = stmt.where(col(Lesson.status).in_(STUDENT_VISIBLE_STATUSES))
    lessons = session.exec(stmt.order_by(Lesson.session_no)).all()
    return CourseDetail(
        **_course_out(session, course, user).model_dump(),
        lessons=[LessonBrief.model_validate(l, from_attributes=True) for l in lessons],
    )


@router.get("/{course_id}/students", response_model=list[CourseStudent], summary="등록 학생 목록 (교사)")
def list_students(
    course_id: int, session: Session = Depends(get_session), teacher: User = Depends(require_teacher)
) -> list[CourseStudent]:
    course = get_owned_course(session, course_id, teacher)
    rows = session.exec(
        select(User, Enrollment.joined_at)
        .join(Enrollment, Enrollment.student_id == User.id)
        .where(Enrollment.course_id == course.id)
        .order_by(Enrollment.joined_at, User.id)
    ).all()
    return [CourseStudent(id=u.id, login_id=u.login_id, name=u.name, joined_at=j) for u, j in rows]
