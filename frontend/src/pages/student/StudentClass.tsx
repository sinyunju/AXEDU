// 수업 중(학생): 재구성 자료 + 페이지별 쉬운 자막. 교사 화면과 묶이지 않고 자기 속도로 이동.
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  ImageIcon,
  ListChecks,
  MessageCircleQuestion,
  MessagesSquare,
  Presentation,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../../api';
import { CaptionList } from '../../components/CaptionList';
import { EasyText } from '../../components/EasyText';
import { PageNav } from '../../components/PageNav';
import { BackLink, Empty, ErrorView, Loading } from '../../components/ui';
import { useAsync } from '../../hooks/useAsync';
import { useLiveLesson } from '../../hooks/useLiveLesson';

export function StudentClass() {
  const { lessonId = '' } = useParams();
  const { data: lesson, loading, error } = useAsync(() => api.getLesson(lessonId), [lessonId]);
  const live = useLiveLesson(lesson ? lessonId : undefined, 'student');
  const [pageNo, setPageNo] = useState(1);
  const [showOriginal, setShowOriginal] = useState(false);
  const { loadPage } = live;

  useEffect(() => {
    if (lesson) loadPage(pageNo);
  }, [lesson, pageNo, loadPage]);

  if (loading) return <Loading />;
  if (error || !lesson) return <ErrorView message={error} />;
  if (live.rejected) return <ErrorView message={live.rejected} />;

  const page = lesson.pages[pageNo - 1] ?? lesson.pages[0];
  const pageCaptions = live.captionsOf(pageNo);
  const status = live.liveStatus ?? lesson.status;
  const teacherPage = live.teacherPage;

  return (
    <div className="stack class-page">
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

      {/* 태블릿·PC: 왼쪽 수업 내용 / 오른쪽 그림 + 선생님 설명. 휴대폰: 위아래로 쌓임 */}
      <div className="class-grid">
        <div className="stack">
          <section className="card stack">
            <EasyText text={page.easyText} terms={page.terms} />
            <button className="btn btn-ghost btn-sm" style={{ alignSelf: 'flex-start' }} onClick={() => setShowOriginal((v) => !v)}>
              {showOriginal ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              {showOriginal ? '원래 자료 접기' : '원래 자료 보기'}
            </button>
            {showOriginal &&
              (page.originalText ? (
                <p className="original-box">{page.originalText}</p>
              ) : (
                page.originalImageUrl && <img src={page.originalImageUrl} alt={`${page.index}쪽 원래 자료`} />
              ))}
          </section>

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
        </div>

        <div className="stack class-side">
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

      {status === 'live' && teacherPage !== null && teacherPage !== pageNo && (
        <button className="follow-pill" onClick={() => setPageNo(teacherPage)}>
          <span className="live-dot" /> 선생님은 지금 {teacherPage}쪽 · 따라가기
        </button>
      )}
    </div>
  );
}
