// 수업 중(학생): 수업 자료(크게, 필기 가능) | 쉬운 설명·선생님 설명 패널. 교사 화면과 묶이지 않고 자기 속도로 이동.
// - 패널 너비는 가운데 손잡이를 끌어서 조절 (이 브라우저에 기억)
// - 전체화면에서도 설명 패널은 오른쪽에 그대로 보임
// - 선생님이 레이저를 쓰면 같은 페이지를 보고 있을 때 빨간 점으로 보임
import {
  BookOpenText,
  CheckCircle2,
  GripVertical,
  ImageIcon,
  ListChecks,
  Maximize,
  MessageCircleQuestion,
  MessagesSquare,
  Minimize,
  Presentation,
} from 'lucide-react';
import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../../api';
import { CaptionList } from '../../components/CaptionList';
import { EasyText } from '../../components/EasyText';
import { PageNav } from '../../components/PageNav';
import { SaveStateLabel } from '../../components/SaveStateLabel';
import { SlideBoard } from '../../components/SlideBoard';
import { BackLink, Empty, ErrorView, Loading } from '../../components/ui';
import { useAnnotations } from '../../hooks/useAnnotations';
import { useAsync } from '../../hooks/useAsync';
import { useFullscreen } from '../../hooks/useFullscreen';
import { useLiveLesson } from '../../hooks/useLiveLesson';
import { usePageKeys } from '../../hooks/usePageKeys';

const SIDE_KEY = 'class.sideWidth';
const SIDE_MIN = 280;
const SIDE_DEFAULT = 380;

function loadSideWidth() {
  try {
    const v = Number(localStorage.getItem(SIDE_KEY));
    return v >= SIDE_MIN ? v : SIDE_DEFAULT;
  } catch {
    return SIDE_DEFAULT;
  }
}

export function StudentClass() {
  const { lessonId = '' } = useParams();
  const { data: lesson, loading, error } = useAsync(() => api.getLesson(lessonId), [lessonId]);
  const live = useLiveLesson(lesson ? lessonId : undefined, 'student');
  const notes = useAnnotations(lesson ? lessonId : undefined);
  const [pageNo, setPageNo] = useState(1);
  const [sideW, setSideW] = useState(loadSideWidth);
  const presentRef = useRef<HTMLDivElement>(null);
  const splitRef = useRef<HTMLDivElement>(null);
  const fs = useFullscreen(presentRef);
  const { loadPage } = live;
  const total = lesson?.pages.length ?? 0;

  useEffect(() => {
    if (lesson) loadPage(pageNo);
  }, [lesson, pageNo, loadPage]);

  // 전체화면에서는 ←/→, PageUp/PageDown으로 페이지 이동
  usePageKeys(fs.on, (delta) => setPageNo((p) => Math.min(Math.max(p + delta, 1), total || 1)));

  // ---------- 패널 너비 조절 ----------
  const clampSide = (w: number) => {
    const max = Math.max(SIDE_MIN, (splitRef.current?.clientWidth ?? 1200) * 0.6);
    return Math.round(Math.min(Math.max(w, SIDE_MIN), max));
  };
  const saveSide = (w: number) => {
    try {
      localStorage.setItem(SIDE_KEY, String(w));
    } catch {
      /* 무시 */
    }
  };
  const onHandleDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onHandleMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!e.currentTarget.hasPointerCapture(e.pointerId) || !splitRef.current) return;
    const right = splitRef.current.getBoundingClientRect().right;
    setSideW(clampSide(right - e.clientX - 7));
  };
  const onHandleUp = () => saveSide(sideW);
  const onHandleKey = (e: React.KeyboardEvent) => {
    const step = e.key === 'ArrowLeft' ? 24 : e.key === 'ArrowRight' ? -24 : 0;
    if (!step) return;
    e.preventDefault();
    e.stopPropagation();
    const w = clampSide(sideW + step);
    setSideW(w);
    saveSide(w);
  };

  if (loading) return <Loading />;
  if (error || !lesson) return <ErrorView message={error} />;
  if (live.rejected) return <ErrorView message={live.rejected} />;

  const page = lesson.pages[pageNo - 1] ?? lesson.pages[0];
  const pageCaptions = live.captionsOf(pageNo);
  const status = live.liveStatus ?? lesson.status;
  const teacherPage = live.teacherPage;

  return (
    <div className="stack">
      <BackLink to={`/student/courses/${lesson.courseId}`}>수업 목록</BackLink>

      <div className="pill-title">
        {status === 'live' && <span className="live-dot" aria-label="수업 중" />}
        <span className="grow">
          {lesson.sessionNo}회차 · {lesson.title}
        </span>
        <span className="divider" />
        <span>
          {pageNo} / {lesson.pages.length}
        </span>
      </div>

      {status === 'ended' && (
        <div className="ended-banner">
          <CheckCircle2 size={20} />
          <span className="grow">수업이 끝났어요. 확인 문제를 풀어 볼까요?</span>
          <Link to={`/class/${lessonId}/quiz`} className="btn btn-primary btn-sm">
            문제 풀기
          </Link>
        </div>
      )}

      <div ref={presentRef} className={`present ${fs.pseudo ? 'pseudo-fullscreen' : ''}`}>
        {fs.on && (
          <div className="present-bar">
            {status === 'live' && <span className="live-dot" aria-label="수업 중" />}
            <strong className="grow">
              {lesson.sessionNo}회차 · {lesson.title}
            </strong>
            <PageNav current={pageNo} total={lesson.pages.length} onChange={setPageNo} />
          </div>
        )}

        {/* 태블릿·PC: 왼쪽 수업 자료 | 손잡이 | 오른쪽 설명. 휴대폰: 위아래로 쌓임 */}
        <div className="class-split" ref={splitRef} style={{ '--side-w': `${sideW}px` } as CSSProperties}>
          <div className="class-main">
            <SlideBoard
              pageKey={pageNo}
              imageUrl={page.originalImageUrl}
              fallback={page.originalText || page.easyText}
              alt={`${page.index}쪽 수업 자료`}
              strokes={notes.strokesOf(pageNo)}
              onStrokesChange={(strokes) => notes.setStrokes(pageNo, strokes)}
              remotePointer={status === 'live' ? live.pointerOn(pageNo) : null}
              fill={fs.on}
              toolbarEnd={
                <>
                  <SaveStateLabel state={notes.saveState} />
                  <button className="tool-btn" onClick={fs.toggle} title={fs.on ? '전체화면 나가기' : '전체화면'} aria-label={fs.on ? '전체화면 나가기' : '전체화면'}>
                    {fs.on ? <Minimize size={18} /> : <Maximize size={18} />}
                  </button>
                </>
              }
            />

            {!fs.on && (
              <>
                <PageNav current={pageNo} total={lesson.pages.length} onChange={setPageNo} />
                <div className="page-dots" role="tablist" aria-label="페이지">
                  {lesson.pages.map((p) => (
                    <button
                      key={p.index}
                      role="tab"
                      aria-selected={p.index === pageNo}
                      className={`page-dot ${p.index === pageNo ? 'active' : ''} ${status === 'live' && p.index === teacherPage ? 'teacher' : ''}`}
                      onClick={() => setPageNo(p.index)}
                    >
                      {p.index}
                      {live.countOf(p.index) > 0 && <span className="badge">{live.countOf(p.index)}</span>}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>

          <div
            className="split-handle"
            role="separator"
            aria-orientation="vertical"
            aria-label="설명 패널 너비 조절 (←, →)"
            aria-valuenow={sideW}
            tabIndex={0}
            onPointerDown={onHandleDown}
            onPointerMove={onHandleMove}
            onPointerUp={onHandleUp}
            onKeyDown={onHandleKey}
          >
            <GripVertical size={16} />
          </div>

          <div className="stack class-side">
            {page.easyText.trim() && (
              <section className="card">
                <div className="card-title">
                  <BookOpenText size={20} />
                  <h3>쉬운 설명</h3>
                </div>
                <EasyText text={page.easyText} terms={page.terms} />
              </section>
            )}

            {page.image?.approved && page.image.url && (
              <section className="card card-tight">
                <div className="card-title" style={{ marginBottom: 10 }}>
                  <ImageIcon size={20} />
                  <h3>그림으로 보기</h3>
                </div>
                <img src={page.image.url} alt={`${page.index}쪽 내용을 나타낸 그림`} />
              </section>
            )}

            <section className="card">
              <div className="card-title">
                <MessagesSquare size={20} />
                <h3>선생님 설명</h3>
                <span className="chip chip-blue count">{pageCaptions.items.length}개</span>
              </div>
              {pageCaptions.items.length === 0 ? (
                <Empty icon={<Presentation size={24} />}>
                  <span className="small">아직 이 페이지 설명이 없어요.</span>
                </Empty>
              ) : (
                <CaptionList items={pageCaptions.items} hardWords={[...page.terms, ...pageCaptions.hardWords]} />
              )}
            </section>
          </div>
        </div>

        {status === 'live' && teacherPage !== null && teacherPage !== pageNo && (
          <button className="follow-pill" onClick={() => setPageNo(teacherPage)}>
            <span className="live-dot" /> 선생님은 지금 {teacherPage}쪽 · 따라가기
          </button>
        )}
      </div>

      <div className="action-grid" style={{ marginTop: 8 }}>
        <Link to={`/class/${lessonId}/quiz`} className="action-tile">
          <div className="action-icon">
            <ListChecks size={22} />
          </div>
          확인 문제 풀기
          <span>배운 내용을 확인해요</span>
        </Link>
        <Link to={`/class/${lessonId}/chat`} className="action-tile">
          <div className="action-icon">
            <MessageCircleQuestion size={22} />
          </div>
          궁금한 점 물어보기
          <span>수업 내용 안에서 답해요</span>
        </Link>
      </div>

    </div>
  );
}
