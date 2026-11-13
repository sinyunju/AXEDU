// 수업 중(교사): 들어오면 수업 시작(POST /start) → 자료를 넘기며 설명(음성 인식) → 수업 끝내기(/end) → 퀴즈 만들기
import {
  AlertCircle,
  AudioLines,
  CheckCircle2,
  FileText,
  ListChecks,
  Loader2,
  Mic,
  MicOff,
  Play,
  Send,
  Sparkles,
  Square,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../../api';
import type { QuizItem } from '../../api/types';
import { CaptionList } from '../../components/CaptionList';
import { PageNav } from '../../components/PageNav';
import { BackLink, Empty, ErrorView, Loading } from '../../components/ui';
import { useAsync } from '../../hooks/useAsync';
import { useLiveLesson } from '../../hooks/useLiveLesson';
import { useSpeechRecognition } from '../../hooks/useSpeechRecognition';

export function LiveClass() {
  const { lessonId = '' } = useParams();
  const { data: lesson, loading, error } = useAsync(() => api.getLesson(lessonId), [lessonId]);
  const live = useLiveLesson(lessonId, 'teacher');
  const [pageNo, setPageNo] = useState(1);
  const [manual, setManual] = useState('');
  const [startError, setStartError] = useState('');
  const [ending, setEnding] = useState(false);
  const [quiz, setQuiz] = useState<QuizItem[] | null>(null);
  const [quizBusy, setQuizBusy] = useState(false);
  const [quizError, setQuizError] = useState('');
  const pageRef = useRef(pageNo);
  pageRef.current = pageNo;
  const { setLiveStatus, send, loadPage } = live;

  // 들어오면 수업 시작 (이미 진행 중이면 그대로, 끝난 수업이면 다시 시작)
  useEffect(() => {
    if (!lesson) return;
    let cancelled = false;
    (async () => {
      try {
        const started = await api.startLesson(lesson.id);
        if (cancelled) return;
        const first = lesson.status === 'approved' ? 1 : lesson.currentPage || 1;
        setLiveStatus(started.status);
        setPageNo(first);
        send({ type: 'page_change', pageIndex: first }); // 학생들에게 지금 페이지 알림
      } catch (e) {
        if (!cancelled) setStartError((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [lesson, setLiveStatus, send]);

  useEffect(() => {
    loadPage(pageNo);
  }, [pageNo, loadPage]);

  const isLive = live.liveStatus === 'live';
  const speech = useSpeechRecognition((text) => {
    if (text) send({ type: 'transcript', pageIndex: pageRef.current, text }); // 확정된 문장만 들어옴
  });
  const { stop: stopSpeech } = speech;
  useEffect(() => {
    if (!isLive) stopSpeech();
  }, [isLive, stopSpeech]);

  function changePage(n: number) {
    setPageNo(n);
    send({ type: 'page_change', pageIndex: n });
  }

  async function endLesson() {
    if (!window.confirm('수업을 끝낼까요? 남은 설명은 마지막으로 정리돼서 학생 화면에 올라가요.')) return;
    setEnding(true);
    try {
      const ended = await api.endLesson(lessonId);
      setLiveStatus(ended.status);
    } catch (e) {
      setStartError((e as Error).message);
    } finally {
      setEnding(false);
    }
  }

  async function restart() {
    try {
      const started = await api.startLesson(lessonId);
      setLiveStatus(started.status);
      send({ type: 'page_change', pageIndex: pageRef.current });
    } catch (e) {
      setStartError((e as Error).message);
    }
  }

  async function makeQuiz() {
    setQuizBusy(true);
    setQuizError('');
    try {
      setQuiz(await api.createQuiz(lessonId));
    } catch (e) {
      setQuizError((e as Error).message);
    } finally {
      setQuizBusy(false);
    }
  }

  if (loading) return <Loading />;
  if (error || !lesson) return <ErrorView message={error} />;
  if (live.rejected) return <ErrorView message={live.rejected} />;

  const page = lesson.pages[pageNo - 1] ?? lesson.pages[0];
  const pageCaptions = live.captionsOf(pageNo);

  return (
    <div className="stack">
      <BackLink to={`/teacher/courses/${lesson.courseId}`}>회차 목록</BackLink>

      <section className="card live-bar">
        {isLive ? (
          <span className="chip chip-bad">
            <span className="live-dot" /> 수업 중
          </span>
        ) : live.liveStatus === 'ended' ? (
          <span className="chip">수업 끝</span>
        ) : (
          <span className="chip chip-blue">
            <Loader2 size={13} className="spin" /> 시작하는 중
          </span>
        )}
        <h2 className="grow">
          {lesson.sessionNo}회차 · {lesson.title}
        </h2>
        {isLive && (
          <>
            {speech.supported ? (
              <button
                className={`btn mic-btn ${speech.listening ? 'btn-danger on' : 'btn-primary'}`}
                onClick={speech.listening ? speech.stop : speech.start}
              >
                {speech.listening ? <MicOff size={19} /> : <Mic size={19} />}
                {speech.listening ? '음성 인식 끄기' : '음성 인식 켜기'}
              </button>
            ) : (
              <span className="chip chip-warn">
                <AlertCircle size={14} /> 이 브라우저는 음성 인식을 지원하지 않아요 (크롬 권장)
              </span>
            )}
            <button className="btn" onClick={endLesson} disabled={ending}>
              <Square size={15} /> {ending ? '끝내는 중…' : '수업 끝내기'}
            </button>
          </>
        )}
      </section>

      {(startError || live.serverError) && (
        <div className="interim">
          <AlertCircle size={17} /> {startError || live.serverError}
        </div>
      )}

      {live.liveStatus === 'ended' && (
        <section className="card stack">
          <div className="row" style={{ gap: 12 }}>
            <CheckCircle2 size={22} style={{ color: 'var(--ok)' }} />
            <h3 className="grow">수업이 끝났어요</h3>
            <button className="btn btn-sm" onClick={restart}>
              <Play size={15} /> 수업 다시 시작
            </button>
          </div>
          {quiz ? (
            <div className="stack-sm">
              <p className="muted small">확인 문제 {quiz.length}개가 준비됐어요. 학생들이 수업 화면에서 풀 수 있어요.</p>
              <ol className="quiz-preview">
                {quiz.map((q) => (
                  <li key={q.id}>{q.question}</li>
                ))}
              </ol>
            </div>
          ) : (
            <div className="row">
              <button className="btn btn-primary" onClick={makeQuiz} disabled={quizBusy}>
                {quizBusy ? <Loader2 size={17} className="spin" /> : <ListChecks size={17} />}
                {quizBusy ? '퀴즈 만드는 중… (10~25초)' : '퀴즈 만들기'}
              </button>
              <span className="muted small">수업 자료와 선생님 설명으로 OX·3지선다 문제를 만들어요.</span>
            </div>
          )}
          {quizError && <p className="error-text">{quizError}</p>}
        </section>
      )}

      <PageNav current={pageNo} total={lesson.pages.length} onChange={changePage} />

      <div className="two-col">
        <section className="card card-soft stack sticky-col">
          <div className="card-title" style={{ marginBottom: 0 }}>
            <FileText size={20} />
            <h3>수업 자료</h3>
            <span className="chip count">{page.index}쪽</span>
          </div>
          {page.originalImageUrl && <img src={page.originalImageUrl} alt={`${page.index}쪽 원본`} />}
          {page.originalText && <p style={{ fontSize: '1.1rem', lineHeight: 1.9 }}>{page.originalText}</p>}
        </section>

        <section className="card stack">
          <div className="card-title" style={{ marginBottom: 0 }}>
            <Sparkles size={20} />
            <h3>변환된 쉬운 설명</h3>
            <span className="chip chip-blue count">{pageCaptions.items.length}개</span>
          </div>

          {speech.interim && (
            <div className="interim">
              <AudioLines size={17} /> {speech.interim}
            </div>
          )}

          {pageCaptions.items.length === 0 ? (
            <Empty icon={<Mic size={24} />}>
              <span className="small">
                설명을 시작하면 쉬운 문장으로 바뀌어
                <br />이 페이지에 쌓여요.
              </span>
            </Empty>
          ) : (
            <CaptionList items={pageCaptions.items} hardWords={pageCaptions.hardWords} />
          )}

          {/* 마이크가 안 될 때·리플레이 모드 대비 수동 입력 */}
          <form
            className="composer"
            onSubmit={(e) => {
              e.preventDefault();
              const text = manual.trim();
              if (text) send({ type: 'transcript', pageIndex: pageNo, text });
              setManual('');
            }}
          >
            <input
              placeholder={isLive ? '설명을 직접 입력할 수도 있어요' : '수업 중에만 보낼 수 있어요'}
              value={manual}
              disabled={!isLive}
              onChange={(e) => setManual(e.target.value)}
            />
            <button className="btn btn-primary btn-icon" aria-label="보내기" disabled={!isLive || !manual.trim()}>
              <Send size={17} />
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
