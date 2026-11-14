// 교사: 과목 상세 — 초대 코드, 회차 목록, 회차 추가(PDF와 함께), 과목·회차 정보 수정
import { AlertCircle, CalendarPlus, Check, Clock, Copy, FileText, Loader2, Pencil, Play, Users } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../../api';
import { OPEN_TO_STUDENTS, type Course, type LessonSummary } from '../../api/types';
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

/** 과목 이름·설명 수정 (제목 카드 안) */
function CourseEditForm({ course, onDone, onCancel }: { course: Course; onDone: () => void; onCancel: () => void }) {
  const [name, setName] = useState(course.name);
  const [subject, setSubject] = useState(course.subject);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api.updateCourse(course.id, { name: name.trim(), subject: subject.trim() });
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="hero-edit stack-sm" onSubmit={onSubmit}>
      <label className="field">
        <span>과목 이름</span>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} required maxLength={100} autoFocus />
      </label>
      <label className="field">
        <span>설명 (선택)</span>
        <input className="input" value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={1000} placeholder="예: 2학년 3반 2학기" />
      </label>
      {error && <p className="hero-error">{error}</p>}
      <div className="row" style={{ gap: 8 }}>
        <button className="btn btn-white btn-sm" disabled={busy || !name.trim()}>
          {busy ? <Loader2 size={15} className="spin" /> : <Check size={15} />} 저장
        </button>
        <button type="button" className="btn btn-ghost-light btn-sm" onClick={onCancel} disabled={busy}>
          취소
        </button>
      </div>
    </form>
  );
}

/** 회차 번호·제목·날짜 수정 (목록 안에서 그 줄을 바꿔서 보여 줌). 수업 자료(PDF)는 그대로 */
function LessonEditRow({ lesson, onDone, onCancel }: { lesson: LessonSummary; onDone: () => void; onCancel: () => void }) {
  const [sessionNo, setSessionNo] = useState(String(lesson.sessionNo));
  const [title, setTitle] = useState(lesson.title);
  const [classDate, setClassDate] = useState(lesson.classDate ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const no = Number(sessionNo);
  const valid = Number.isInteger(no) && no >= 1 && title.trim().length > 0;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!valid) return;
    setBusy(true);
    setError('');
    try {
      await api.updateLessonInfo(lesson.id, lesson.courseId, { sessionNo: no, title: title.trim(), classDate: classDate || null });
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="lesson-item editing">
      <form className="lesson-edit" onSubmit={onSubmit}>
        <label className="field" style={{ width: 84 }}>
          <span>회차</span>
          <input className="input" type="number" min={1} inputMode="numeric" value={sessionNo} onChange={(e) => setSessionNo(e.target.value)} required />
        </label>
        <label className="field grow">
          <span>수업 제목</span>
          <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={200} autoFocus />
        </label>
        <label className="field">
          <span>수업 날짜</span>
          <input className="input" type="date" value={classDate} onChange={(e) => setClassDate(e.target.value)} />
        </label>
        <div className="lesson-edit-actions">
          <button className="btn btn-primary btn-sm" disabled={busy || !valid}>
            {busy ? <Loader2 size={15} className="spin" /> : <Check size={15} />} 저장
          </button>
          <button type="button" className="btn btn-sm" onClick={onCancel} disabled={busy}>
            취소
          </button>
        </div>
        {error && <p className="error-text lesson-edit-error">{error}</p>}
        <p className="muted small lesson-edit-note">수업 자료(PDF)와 페이지 내용은 그대로예요.</p>
      </form>
    </li>
  );
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
  const [editingCourse, setEditingCourse] = useState(false);
  const [editingLesson, setEditingLesson] = useState<string | null>(null);

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
          {editingCourse ? <span /> : c.subject ? <span className="chip chip-glass">{c.subject}</span> : <span />}
          <span className="row muted-on-blue small">
            <Users size={16} /> 학생 초대 코드
          </span>
        </div>
        <div className="row between" style={{ alignItems: 'flex-end' }}>
          {editingCourse ? (
            <CourseEditForm
              course={c}
              onCancel={() => setEditingCourse(false)}
              onDone={() => {
                setEditingCourse(false);
                course.reload();
              }}
            />
          ) : (
            <div className="row" style={{ gap: 10, alignItems: 'center' }}>
              <h1 style={{ fontSize: '1.9rem' }}>{c.name}</h1>
              <button className="btn btn-ghost-light btn-sm" onClick={() => setEditingCourse(true)} aria-label="과목 이름·설명 수정">
                <Pencil size={15} /> 수정
              </button>
            </div>
          )}
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
              if (editingLesson === l.id) {
                return (
                  <LessonEditRow
                    key={l.id}
                    lesson={l}
                    onCancel={() => setEditingLesson(null)}
                    onDone={() => {
                      setEditingLesson(null);
                      lessons.reload();
                    }}
                  />
                );
              }
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
                    <button
                      className="btn btn-ghost btn-icon btn-sm"
                      onClick={() => setEditingLesson(l.id)}
                      aria-label={`${l.sessionNo}회차 정보 수정`}
                      title="회차 번호·제목·날짜 수정"
                    >
                      <Pencil size={15} />
                    </button>
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
