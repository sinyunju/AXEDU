// 교사 첫 화면: 왼쪽 일정(주/월), 오른쪽 내 과목 + 과목 개설
import { BookOpen, ChevronRight, KeyRound, Plus, X } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../api';
import { displayName, useAuth } from '../../auth/AuthContext';
import { ScheduleWidget } from '../../components/ScheduleWidget';
import { Empty, ErrorView, Loading } from '../../components/ui';
import { features } from '../../config';
import { useAsync } from '../../hooks/useAsync';
import { randomGreeting } from '../../lib/greetings';

export function TeacherDashboard() {
  const { user } = useAuth();
  const { data: courses, loading, error, reload } = useAsync(() => api.listCourses(), []);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [subject, setSubject] = useState('');
  const [busy, setBusy] = useState(false);
  const [greeting] = useState(randomGreeting); // 화면을 열 때(새로고침 포함) 한 번만 고름

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.createCourse(name, subject);
      setName('');
      setSubject('');
      setCreating(false);
      reload();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <span className="eyebrow">{user && displayName(user)}</span>
          <h2>{greeting}</h2>
          <p>일정을 확인하고, 수업 시간 전에 자료를 준비해 두세요.</p>
        </div>
      </div>

      <div className={features.calendar ? 'home-grid' : 'home-grid no-cal'}>
        {features.calendar && <ScheduleWidget role="teacher" />}

        <aside className="stack home-aside">
          <div className="row between">
            <h3>내 과목</h3>
            {!creating && (
              <button className="btn btn-light btn-sm" onClick={() => setCreating(true)}>
                <Plus size={16} /> 과목 개설
              </button>
            )}
          </div>

          {creating && (
            <form className="card stack" onSubmit={onCreate}>
              <div className="row between">
                <h3>새 과목 만들기</h3>
                <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label="닫기" onClick={() => setCreating(false)}>
                  <X size={18} />
                </button>
              </div>
              <label className="field">
                <span>과목 이름</span>
                <input className="input" placeholder="예: 과학" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
              </label>
              <label className="field">
                <span>설명 (선택)</span>
                <input className="input" placeholder="예: 2학년 3반 2학기" value={subject} onChange={(e) => setSubject(e.target.value)} />
              </label>
              <p className="muted small">만들면 학생들이 입력할 초대 코드(영문·숫자 6자)가 바로 생겨요.</p>
              <button className="btn btn-primary btn-block" disabled={busy}>
                {busy ? '만드는 중…' : '과목 만들기'}
              </button>
            </form>
          )}

          {loading && <Loading />}
          {error && <ErrorView message={error} />}
          {courses?.length === 0 && !creating && (
            <div className="card">
              <Empty icon={<BookOpen size={26} />}>
                <strong>아직 개설한 과목이 없어요</strong>
                <span className="small">‘과목 개설’로 첫 과목을 만들어 보세요.</span>
              </Empty>
            </div>
          )}

          {courses?.map((c, i) => (
            <Link key={c.id} to={`/teacher/courses/${c.id}`} className={`course-card ${i === 0 ? 'featured' : ''}`}>
              <div className="row" style={{ gap: 14, flexWrap: 'nowrap' }}>
                <div className="course-icon">
                  <BookOpen size={24} />
                </div>
                <div className="grow">
                  <h3>{c.name}</h3>
                  <span className="small" style={{ opacity: 0.8 }}>
                    {c.subject}
                  </span>
                </div>
                <ChevronRight size={20} style={{ opacity: 0.6 }} />
              </div>
              <div className="course-foot">
                <span>{c.lessonCount !== undefined ? `회차 ${c.lessonCount}개` : c.subject}</span>
                <span className="row" style={{ gap: 4 }}>
                  <KeyRound size={14} /> 초대 코드 <strong style={{ letterSpacing: '0.12em' }}>{c.joinCode}</strong>
                </span>
              </div>
            </Link>
          ))}
        </aside>
      </div>
    </div>
  );
}
