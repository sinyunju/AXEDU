// 교사(수업 전): AI 변환 진행 → 쉬운 문장·어려운 말·이미지 검토·수정 → 승인
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  FileText,
  ImageIcon,
  Loader2,
  Play,
  Plus,
  RefreshCw,
  Save,
  Sparkles,
  Trash2,
  Wand2,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../../api';
import type { LessonPage } from '../../api/types';
import { PageNav } from '../../components/PageNav';
import { BackLink, ErrorView, Loading, StatusChip } from '../../components/ui';
import { features } from '../../config';
import { useAsync } from '../../hooks/useAsync';
import { daysLabel, formatClassDate } from '../../lib/time';

const POLL_MS = 1500;

export function LessonReview() {
  const { lessonId = '' } = useParams();
  const { data: lesson, setData: setLesson, loading, error } = useAsync(() => api.getLesson(lessonId), [lessonId]);
  const [pageNo, setPageNo] = useState(1);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [actionError, setActionError] = useState('');
  const [imgPrompt, setImgPrompt] = useState('');
  const [imgBusy, setImgBusy] = useState(false);
  const [explaining, setExplaining] = useState<Set<string>>(new Set()); // `${pageIndex}:${word}`

  // AI 변환 중이면 진행률을 주기적으로 확인 (generating → ready)
  const processing = lesson?.status === 'processing';
  useEffect(() => {
    if (!processing) return;
    const t = setInterval(async () => {
      try {
        setLesson(await api.getLesson(lessonId));
      } catch {
        /* 다음 주기에 다시 */
      }
    }, POLL_MS);
    return () => clearInterval(t);
  }, [processing, lessonId, setLesson]);

  if (loading) return <Loading />;
  if (error || !lesson) return <ErrorView message={error} />;

  async function startGenerate() {
    setActionError('');
    try {
      const s = await api.generateLesson(lesson!.id);
      setLesson({ ...lesson!, status: s.status, progress: s.progress });
    } catch (e) {
      setActionError((e as Error).message);
    }
  }

  const header = (
    <>
      <BackLink to={`/teacher/courses/${lesson.courseId}`}>회차 목록</BackLink>
      <div className="page-head">
        <div>
          <span className="eyebrow">
            {lesson.sessionNo}회차 · {formatClassDate(lesson.classDate)}
            {lesson.classDate && ` · ${daysLabel(lesson.classDate)}`}
          </span>
          <h2>{lesson.title}</h2>
        </div>
        <StatusChip status={lesson.status} />
      </div>
    </>
  );

  // AI 변환 전 / 변환 중
  if (lesson.status === 'uploaded' || lesson.status === 'processing') {
    return (
      <div className="stack narrow-page">
        {header}
        <section className="dropzone" style={{ cursor: 'default' }}>
          <div className="drop-icon">
            {processing ? <Loader2 size={30} className="spin" /> : <Wand2 size={30} />}
          </div>
          {processing ? (
            <>
              <h3>AI가 쉬운 문장으로 바꾸는 중… {lesson.progress}%</h3>
              <div className="progress" style={{ width: '100%', maxWidth: 360, background: 'var(--surface)' }} aria-hidden>
                <div style={{ width: `${lesson.progress}%` }} />
              </div>
              <p className="muted small">{lesson.pages.length}쪽 · 페이지가 많으면 조금 걸려요. 이 화면을 떠나도 계속 진행돼요.</p>
            </>
          ) : (
            <>
              <h3>자료가 올라갔어요 ({lesson.pages.length}쪽)</h3>
              <p className="muted">AI 변환을 시작하면 페이지마다 쉬운 문장과 어려운 말 풀이를 만들어요.</p>
              <button className="btn btn-primary" onClick={startGenerate}>
                <Sparkles size={17} /> AI 변환 시작
              </button>
            </>
          )}
        </section>
        {actionError && <p className="error-text">{actionError}</p>}
      </div>
    );
  }

  const page = lesson.pages[pageNo - 1] ?? lesson.pages[0];

  function updatePage(patch: Partial<LessonPage>) {
    setLesson({ ...lesson!, pages: lesson!.pages.map((p) => (p.index === page.index ? { ...p, ...patch } : p)) });
  }

  /** 단어를 입력하면 AI가 쉬운 뜻을 채움. 응답이 오는 사이 단어가 바뀌었으면 버림 */
  async function explain(i: number, word: string) {
    const w = word.trim();
    if (!w || !features.explainTerm) return;
    const pageIndex = page.index;
    const key = `${pageIndex}:${w}`;
    setExplaining((s) => new Set(s).add(key));
    try {
      const { meaning } = await api.explainTerm(lesson!.id, pageIndex, w);
      setLesson((cur) =>
        cur && {
          ...cur,
          pages: cur.pages.map((p) =>
            p.index === pageIndex
              ? { ...p, terms: p.terms.map((t, j) => (j === i && t.word.trim() === w ? { ...t, meaning } : t)) }
              : p,
          ),
        },
      );
    } finally {
      setExplaining((s) => {
        const next = new Set(s);
        next.delete(key);
        return next;
      });
    }
  }

  async function save() {
    setSaving(true);
    setActionError('');
    try {
      await api.updateLesson(lesson!);
      setSavedAt(new Date());
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function approve() {
    setActionError('');
    try {
      await api.updateLesson(lesson!);
      setLesson(await api.approveLesson(lesson!.id));
    } catch (e) {
      setActionError((e as Error).message);
    }
  }

  async function generateImage() {
    setImgBusy(true);
    setActionError('');
    try {
      const updated = await api.generateImage(lesson!.id, page.index, imgPrompt);
      updatePage({ image: updated.image });
      setImgPrompt('');
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setImgBusy(false);
    }
  }

  async function removeImage() {
    setActionError('');
    try {
      const updated = await api.deleteImage(lesson!.id, page.index);
      updatePage({ image: updated.image });
    } catch (e) {
      setActionError((e as Error).message);
    }
  }

  return (
    <div className="stack">
      {header}

      <div className="card card-tight row between">
        <PageNav current={pageNo} total={lesson.pages.length} onChange={setPageNo} />
        <div className="row">
          {savedAt && <span className="muted small">{savedAt.toLocaleTimeString('ko-KR', { timeStyle: 'short' })} 저장됨</span>}
          <button className="btn btn-sm" onClick={save} disabled={saving}>
            <Save size={15} /> {saving ? '저장 중…' : '저장'}
          </button>
          {lesson.status === 'review' ? (
            <button className="btn btn-dark btn-sm" onClick={approve}>
              <CheckCircle2 size={15} /> 전체 승인 · 학생에게 공개
            </button>
          ) : (
            <Link to={`/teacher/lessons/${lesson.id}/live`} className="btn btn-primary btn-sm">
              <Play size={15} /> {lesson.status === 'live' ? '수업 화면' : lesson.status === 'ended' ? '다시 시작' : '수업 시작'}
            </Link>
          )}
        </div>
      </div>

      {actionError && (
        <div className="interim">
          <AlertCircle size={17} /> {actionError}
        </div>
      )}

      <div className="two-col">
        <section className="card card-soft stack sticky-col">
          <div className="card-title" style={{ marginBottom: 0 }}>
            <FileText size={20} />
            <h3>원본 자료</h3>
            <span className="chip count">{page.index}쪽</span>
          </div>
          {page.originalImageUrl && <img src={page.originalImageUrl} alt={`원본 ${page.index}쪽`} />}
          {page.originalText && <p style={{ lineHeight: 1.9 }}>{page.originalText}</p>}
        </section>

        <section className="card stack">
          <div className="card-title" style={{ marginBottom: 0 }}>
            <Wand2 size={20} />
            <h3>쉬운 문장</h3>
            <span className="chip chip-blue count">AI 초안 · 수정 가능</span>
          </div>
          <textarea
            className="input"
            rows={8}
            value={page.easyText}
            placeholder="한 줄에 한 문장씩 적어 주세요"
            onChange={(e) => updatePage({ easyText: e.target.value })}
          />
          <p className="muted small" style={{ marginTop: -8 }}>한 줄이 한 문장이에요. 학생 화면에도 줄마다 나눠서 보여요.</p>

          <div className="divider-line" />

          <div className="section-label">
            <BookOpen size={17} /> 어려운 말 풀이
          </div>
          {page.terms.map((t, i) => {
            const busy = explaining.has(`${page.index}:${t.word.trim()}`);
            return (
              <div key={i} className={`term-row ${features.explainTerm ? '' : 'no-ai'}`}>
                <input
                  className="input"
                  placeholder="단어"
                  value={t.word}
                  onChange={(e) =>
                    updatePage({ terms: page.terms.map((x, j) => (j === i ? { ...x, word: e.target.value } : x)) })
                  }
                  // 단어를 다 쓰고 나가면(포커스 이동·Enter) 뜻이 비어 있을 때만 자동 생성
                  onBlur={() => !t.meaning.trim() && explain(i, t.word)}
                  onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
                />
                <input
                  className="input"
                  placeholder={
                    busy ? 'AI가 쉬운 뜻을 만드는 중…' : features.explainTerm ? '쉬운 뜻 (단어를 입력하면 자동으로 채워져요)' : '쉬운 뜻'
                  }
                  value={t.meaning}
                  disabled={busy}
                  onChange={(e) =>
                    updatePage({ terms: page.terms.map((x, j) => (j === i ? { ...x, meaning: e.target.value } : x)) })
                  }
                />
                {features.explainTerm && (
                  <button
                    className="btn btn-ghost btn-icon btn-sm"
                    title="AI로 뜻 다시 만들기"
                    aria-label="AI로 뜻 다시 만들기"
                    disabled={busy || !t.word.trim()}
                    onClick={() => explain(i, t.word)}
                  >
                    <RefreshCw size={16} className={busy ? 'spin' : ''} />
                  </button>
                )}
                <button
                  className="btn btn-ghost btn-icon btn-sm"
                  title="삭제"
                  aria-label="삭제"
                  onClick={() => updatePage({ terms: page.terms.filter((_, j) => j !== i) })}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            );
          })}
          <button
            className="btn btn-soft btn-sm"
            style={{ alignSelf: 'flex-start' }}
            onClick={() => updatePage({ terms: [...page.terms, { word: '', meaning: '' }] })}
          >
            <Plus size={16} /> 단어 추가
          </button>

          <div className="divider-line" />

          <div className="section-label">
            <ImageIcon size={17} /> 이미지
          </div>
          {page.image ? (
            <div className="image-slot">
              {page.image.url ? (
                <img src={page.image.url} alt="" style={{ borderRadius: 0 }} />
              ) : (
                <div className="image-placeholder">
                  <Sparkles size={22} />
                  <span className="small">AI가 이미지가 필요하다고 봤어요</span>
                  {page.image.prompt && <span className="small muted">제안: {page.image.prompt}</span>}
                </div>
              )}
              <div className="row between" style={{ padding: '10px 14px' }}>
                <span className="small muted">이유: {page.image.reason || '-'}</span>
                <button className="btn btn-ghost btn-sm" onClick={removeImage}>
                  <Trash2 size={15} /> 빼기
                </button>
              </div>
            </div>
          ) : (
            <p className="muted small">이 페이지는 이미지 없이 진행해요.</p>
          )}
          <div className="row">
            <input
              className="input grow"
              placeholder={page.image?.prompt ? '비워 두면 AI 제안대로 만들어요' : '이미지로 보여줄 내용 (예: 광합성 재료와 결과)'}
              value={imgPrompt}
              onChange={(e) => setImgPrompt(e.target.value)}
            />
            <button className="btn btn-soft" onClick={generateImage} disabled={imgBusy || (!imgPrompt.trim() && !page.image?.prompt)}>
              {imgBusy ? <Loader2 size={16} className="spin" /> : <Sparkles size={16} />} 생성
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
