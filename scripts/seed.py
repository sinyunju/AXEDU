"""데모용 시드 데이터. 여러 번 실행해도 중복 생성하지 않는다.

실행: .venv/bin/python -m scripts.seed
"""
from sqlmodel import Session, select

from app.db import get_engine, init_db
from app.models import Course, Enrollment, Role, User
from app.security import hash_password

DEMO_PASSWORD = "pass1234"
TEACHER = ("teacher1", "김선생")
STUDENTS = [("student1", "이학생"), ("student2", "박학생"), ("student3", "최학생")]
COURSE_NAME = "과학"
COURSE_INVITE_CODE = "DEMO01"


def _get_or_create_user(session: Session, login_id: str, name: str, role: Role) -> User:
    user = session.exec(select(User).where(User.login_id == login_id)).first()
    if user is None:
        user = User(login_id=login_id, password_hash=hash_password(DEMO_PASSWORD), name=name, role=role)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def seed(session: Session) -> dict:
    teacher = _get_or_create_user(session, *TEACHER, Role.teacher)
    students = [_get_or_create_user(session, lid, name, Role.student) for lid, name in STUDENTS]

    course = session.exec(select(Course).where(Course.invite_code == COURSE_INVITE_CODE)).first()
    if course is None:
        course = Course(
            teacher_id=teacher.id, name=COURSE_NAME, description="데모용 과목", invite_code=COURSE_INVITE_CODE
        )
        session.add(course)
        session.commit()
        session.refresh(course)

    for s in students:
        exists = session.exec(
            select(Enrollment).where(Enrollment.course_id == course.id, Enrollment.student_id == s.id)
        ).first()
        if exists is None:
            session.add(Enrollment(course_id=course.id, student_id=s.id))
    session.commit()
    return {"teacher": teacher, "students": students, "course": course}


def main() -> None:
    init_db()
    with Session(get_engine()) as session:
        result = seed(session)
        invite_code = result["course"].invite_code  # 세션이 열려 있을 때 읽기
    print(f"시드 완료 (비밀번호 공통: {DEMO_PASSWORD})")
    print(f"  교사: {TEACHER[0]}")
    print(f"  학생: {', '.join(lid for lid, _ in STUDENTS)}")
    print(f"  과목: {COURSE_NAME} (초대 코드 {invite_code})")


if __name__ == "__main__":
    main()
