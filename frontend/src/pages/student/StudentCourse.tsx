// 학생: 과목의 회차 목록. 선생님이 승인한(approved/live/ended) 회차만 들어갈 수 있음
import { CalendarClock, ChevronRight, Hourglass } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../../api';
import { BackLink, DateBlock, Empty, ErrorView, Loading } from '../../components/ui';
import { useAsync } from '../../hooks/useAsync';
import { OPEN_TO_STUDENTS } from '../../api/types';
import { formatClassDate } from '../../lib/time';

export function StudentCourse() {
  const { courseId = '' } = useParams();
  const course = useAsync(() => api.getCourse(courseId), [courseId]);
  const lessons = useAsync(() => api.listLessons(courseId), [courseId]);

  if (course.loading) return <Loading />;
  if (course.error || !course.data) return <ErrorView message={course.error} />;
  const c = course.data;

  return (
    <div className="stack narrow-page">
      <BackLink to="/student">내 과목</BackLink>

      <section className="hero-card stack-sm">
        {c.subject && (
          <span className="chip chip-glass" style={{ alignSelf: 'flex-start' }}>
            {c.subject}
          </span>
        )}
        <h2>{c.name}</h2>
        <span className="muted-on-blue">{c.teacherName}</span>
      </section>

      <section className="card">
        <div className="card-title">
          <CalendarClock size={20} />
          <h3>수업</h3>
        </div>
        {lessons.loading && <Loading />}
        {lessons.data?.length === 0 && (
          <Empty icon={<CalendarClock size={26} />}>
            <span className="small">아직 열린 수업이 없어요. 선생님이 준비하면 여기에 나타나요.</span>
          </Empty>
        )}
        <ul className="lesson-list">
          {lessons.data?.map((l) => {
            const ready = OPEN_TO_STUDENTS.includes(l.status);
            const inner = (
              <>
                <DateBlock sessionNo={l.sessionNo} date={l.classDate} />
                <div className="lesson-info">
                  <strong>{l.title}</strong>
                  <div className="lesson-meta">
                    <span>{formatClassDate(l.classDate)}</span>
                    {l.status === 'live' ? (
                      <span className="chip chip-bad">
                        <span className="live-dot" /> 수업 중
                      </span>
                    ) : l.status === 'ended' ? (
                      <span className="chip">수업 끝 · 복습할 수 있어요</span>
                    ) : ready ? (
                      <span className="chip chip-ok">들어갈 수 있어요</span>
                    ) : (
                      <span className="chip">
                        <Hourglass size={13} /> 준비 중
                      </span>
                    )}
                  </div>
                </div>
                {ready && <ChevronRight size={22} style={{ color: 'var(--primary-text)' }} />}
              </>
            );
            return ready ? (
              <li key={l.id}>
                <Link to={`/class/${l.id}`} className="lesson-item ready" style={{ color: 'inherit' }}>
                  {inner}
                </Link>
              </li>
            ) : (
              <li key={l.id} className="lesson-item" style={{ opacity: 0.7 }}>
                {inner}
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
