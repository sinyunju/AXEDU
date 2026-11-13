// 교사: 과목 상세 — 초대 코드, 회차 목록, 회차 추가(PDF와 함께)
import { AlertCircle, CalendarPlus, Check, Clock, Copy, FileText, Loader2, Play, Users } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../../api';
import { OPEN_TO_STUDENTS, type LessonSummary } from '../../api/types';
import { BackLink, DateBlock, Empty, ErrorView, Loading, StatusChip } from '../../components/ui';
import { useAsync } from '../../hooks/useAsync';
import { daysLabel, formatClassDate, todayInput } from '../../lib/time';

function LessonActions({ l }: { l: LessonSummary }) {
  const review = `/teacher/lessons/${l.id}/review`;
  const liveUrl = `/teacher/lessons/${l.id}/live`;
  switch (l.status) {
    case 'uploaded':
      return (
        <Link to={review} className="btn btn-soft btn-sm">
          AI 변환하기
        </Link>
      );
    case 'processing':
      return (
        <Link to={review} className="btn btn-sm">
          <Loader2 size={15} className="spin" /> {l.progress}%
        </Link>
      );
    case 'review':
      return (
        <Link to={review} className="btn btn-soft btn-sm">
          검토하기
        </Link>
      );
    case 'live':
      return (
        <Link to={liveUrl} className="btn btn-primary btn-sm">
          <span className="live-dot" /> 수업 화면
        </Link>
      );
    default: // approved, ended
      return (
        <>
          <Link to={review} className="btn btn-sm">
            검토
          </Link>
          <Link to={liveUrl} className="btn btn-primary btn-sm">
            <Play size={15} /> {l.status === 'ended' ? '다시 시작' : '수업 시작'}
          </Link>
        </>
      );
  }
}

export function CourseDetail() {
  const { courseId = '' } = useParams();
  const navigate = useNavigate();
  const course = useAsync(() => api.getCourse(courseId), [courseId]);
  const lessons = useAsync(() => api.listLessons(courseId), [courseId]);
  const nextSession = Math.max(0, ...(lessons.data ?? []).map((l) => l.sessionNo)) + 1;
  const [sessionNo, setSessionNo] = useState('');
  const [title, setTitle] = useState('');
  const [classDate, setClassDate] = useState(todayInput());
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState<'' | 'upload' | 'generate'>('');
  const [formError, setFormError] = useState('');
  const [copied, setCopied] = useState(false);

  async function onAdd(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setFormError('');
    try {
      setBusy('upload');
      const lesson = await api.createLesson(courseId, {
        file,
        sessionNo: Number(sessionNo) || nextSession,
        title: title.trim(),
        classDate: classDate || undefined,
      });
      setBusy('generate');
      await api.generateLesson(lesson.id); // 올리자마자 AI 변환 시작
      navigate(`/teacher/lessons/${lesson.id}/review`);
    } catch (err) {
      setFormError((err as Error).message);
      lessons.reload();
    } finally {
      setBusy('');
    }
  }

  async function copyCode(code: string) {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* 클립보드 권한이 없으면 무시 */
    }
  }

  if (course.loading) return <Loading />;
  if (course.error || !course.data) return <ErrorView message={course.error} />;
  const c = course.data;

  return (
    <div className="stack">
      <BackLink to="/teacher">내 과목</BackLink>

      <section className="hero-card stack">
        <div className="row between">
          {c.subject ? <span className="chip chip-glass">{c.subject}</span> : <span />}
          <span className="row muted-on-blue small">
            <Users size={16} /> 학생 초대 코드
          </span>
        </div>
        <div className="row between" style={{ alignItems: 'flex-end' }}>
          <h1 style={{ fontSize: '1.9rem' }}>{c.name}</h1>
          {c.joinCode && (
            <div className="code-box">
              <strong>{c.joinCode}</strong>
              <button className="btn btn-white btn-sm" onClick={() => copyCode(c.joinCode!)}>
                {copied ? <Check size={16} /> : <Copy size={16} />} {copied ? '복사됨' : '복사'}
              </button>
            </div>
          )}
        </div>
      </section>

      <div className="course-grid">
        <section className="card">
          <div className="card-title">
            <Clock size={20} />
            <h3>회차</h3>
            <span className="chip count">{lessons.data?.length ?? 0}개</span>
          </div>
          {lessons.loading && <Loading />}
          {lessons.error && <p className="error-text">{lessons.error}</p>}
          {lessons.data?.length === 0 && (
            <Empty icon={<CalendarPlus size={26} />}>
              <strong>아직 회차가 없어요</strong>
              <span className="small">수업 자료 PDF를 올려 첫 회차를 만들어 보세요.</span>
            </Empty>
          )}
          <ul className="lesson-list">
            {lessons.data?.map((l) => {
              const until = daysLabel(l.classDate);
              const late = until === '지남' && !OPEN_TO_STUDENTS.includes(l.status);
              return (
                <li key={l.id} className={`lesson-item ${OPEN_TO_STUDENTS.includes(l.status) ? 'ready' : ''}`}>
                  <DateBlock sessionNo={l.sessionNo} date={l.classDate} />
                  <div className="lesson-info">
                    <strong>{l.title}</strong>
                    <div className="lesson-meta">
                      <span>{formatClassDate(l.classDate)}</span>
                      {until && (
                        <>
                          <span>·</span>
                          <span>{until}</span>
                        </>
                      )}
                      <StatusChip status={l.status} />
                      {late && (
                        <span className="chip chip-bad">
                          <AlertCircle size={13} /> 날짜 지남
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="lesson-actions">
                    <LessonActions l={l} />
                  </div>
                </li>
              );
            })}
          </ul>
        </section>

        <form className="card stack" onSubmit={onAdd}>
          <div className="card-title" style={{ marginBottom: 0 }}>
            <CalendarPlus size={20} />
            <h3>회차 추가</h3>
          </div>
          <div className="row" style={{ flexWrap: 'nowrap', alignItems: 'flex-end' }}>
            <label className="field" style={{ width: 96, flexShrink: 0 }}>
              <span>회차</span>
              <input
                className="input"
                type="number"
                min={1}
                inputMode="numeric"
                placeholder={String(nextSession)}
                value={sessionNo}
                onChange={(e) => setSessionNo(e.target.value)}
              />
            </label>
            <label className="field grow">
              <span>수업 제목</span>
              <input className="input" placeholder="예: 광합성" value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={200} />
            </label>
          </div>
          <label className="field">
            <span>수업 날짜 (선택)</span>
            <input className="input" type="date" value={classDate} onChange={(e) => setClassDate(e.target.value)} />
          </label>
          <label className="field">
            <span>수업 자료 (PDF)</span>
            <label className={`file-pick ${file ? 'picked' : ''}`}>
              <FileText size={18} />
              <span className="grow">{file ? file.name : 'PDF 파일 고르기'}</span>
              <input type="file" accept="application/pdf,.pdf" hidden onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </label>
          </label>
          {formError && <p className="error-text">{formError}</p>}
          <button className="btn btn-primary btn-block" disabled={!!busy || !file || !title.trim()}>
            {busy === 'upload' ? (
              <>
                <Loader2 size={16} className="spin" /> 자료 올리는 중…
              </>
            ) : busy === 'generate' ? (
              <>
                <Loader2 size={16} className="spin" /> AI 변환 시작하는 중…
              </>
            ) : (
              '올리고 AI 변환 시작'
            )}
          </button>
          <p className="muted small">AI가 페이지마다 쉬운 문장을 만들면, 검토·승인해야 학생에게 보여요.</p>
        </form>
      </div>
    </div>
  );
}
