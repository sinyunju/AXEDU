// 학생 첫 화면: 왼쪽 일정(주/월), 오른쪽 내 과목 + 과목 코드로 참여
import { BookOpen, ChevronRight, KeyRound, Plus } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../api';
import { useAuth } from '../../auth/AuthContext';
import { ScheduleWidget } from '../../components/ScheduleWidget';
import { Empty, ErrorView, Loading } from '../../components/ui';
import { config, features } from '../../config';
import { useAsync } from '../../hooks/useAsync';

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return '좋은 아침이에요';
  if (h < 18) return '좋은 오후예요';
  return '오늘도 수고했어요';
}

export function StudentHome() {
  const { user } = useAuth();
  const { data: courses, loading, error, reload } = useAsync(() => api.listCourses(), []);
  const [code, setCode] = useState('');
  const [joinError, setJoinError] = useState('');
  const [busy, setBusy] = useState(false);

  async function onJoin(e: FormEvent) {
    e.preventDefault();
    setJoinError('');
    setBusy(true);
    try {
      await api.joinCourse(code);
      setCode('');
      reload();
    } catch (err) {
      setJoinError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <span className="eyebrow">{new Date().toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'long' })}</span>
          <h2>
            {user?.name}님, {greeting()}
          </h2>
        </div>
      </div>

      <div className={features.calendar ? 'home-grid' : 'home-grid no-cal'}>
        {features.calendar && <ScheduleWidget role="student" />}

        <aside className="stack home-aside">
          <h3>내 과목</h3>
          {loading && <Loading />}
          {error && <ErrorView message={error} />}
          {courses?.length === 0 && (
            <div className="card">
              <Empty icon={<BookOpen size={26} />}>
                <strong>아직 참여한 과목이 없어요</strong>
                <span className="small">선생님께 받은 초대 코드를 아래에 넣어 주세요.</span>
              </Empty>
            </div>
          )}

          {courses?.map((c, i) => (
            <Link key={c.id} to={`/student/courses/${c.id}`} className={`course-card ${i === 0 ? 'featured' : ''}`}>
              <div className="row" style={{ gap: 14, flexWrap: 'nowrap' }}>
                <div className="course-icon">
                  <BookOpen size={24} />
                </div>
                <div className="grow">
                  <h3>{c.name}</h3>
                  <span className="small" style={{ opacity: 0.8 }}>
                    {c.teacherName} · {c.subject}
                  </span>
                </div>
                <ChevronRight size={22} style={{ opacity: 0.7 }} />
              </div>
            </Link>
          ))}

          <form className="card stack" onSubmit={onJoin}>
            <div className="card-title" style={{ marginBottom: 0 }}>
              <KeyRound size={20} />
              <h3>과목 참여하기</h3>
            </div>
            <p className="muted small">선생님이 알려 준 초대 코드(영문·숫자 6자)를 넣으면 그 과목의 수업을 볼 수 있어요.</p>
            <input
              className="input input-code"
              maxLength={6}
              autoCapitalize="characters"
              autoComplete="off"
              spellCheck={false}
              placeholder="••••••"
              aria-label="초대 코드 6자"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/[^0-9a-zA-Z]/g, '').toUpperCase())}
            />
            {joinError && <p className="error-text center">{joinError}</p>}
            <button className="btn btn-primary btn-block" disabled={code.length !== 6 || busy}>
              <Plus size={18} /> 참여하기
            </button>
            {config.useMock && <p className="muted small center">목 모드 예시 코드: DEMO01</p>}
          </form>
        </aside>
      </div>
    </div>
  );
}
