// 수업 후(학생): 확인 문제. 정답은 서버만 알고 있어서, 다 고른 뒤 제출하면 채점 결과·해설을 받아 보여줌
import { CheckCircle2, ClipboardList, Lightbulb, PartyPopper, RotateCcw, Send } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../../api';
import type { QuizResult } from '../../api/types';
import { BackLink, Empty, ErrorView, Loading } from '../../components/ui';
import { useAsync } from '../../hooks/useAsync';

const letters = ['①', '②', '③', '④', '⑤'];

export function Quiz() {
  const { lessonId = '' } = useParams();
  const { data, loading, error } = useAsync(async () => {
    const [items, past] = await Promise.all([api.getQuiz(lessonId), api.myQuizResults(lessonId)]);
    return { items, last: past[0] ?? null };
  }, [lessonId]);
  const [picked, setPicked] = useState<Record<string, string>>({});
  const [result, setResult] = useState<QuizResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  // 전에 푼 기록이 있으면 마지막 결과를 보여줌
  useEffect(() => {
    if (data?.last) {
      setResult(data.last);
      setPicked(Object.fromEntries(data.last.results.map((r) => [r.questionId, r.answer ?? ''])));
    }
  }, [data]);

  if (loading) return <Loading label="문제를 불러오는 중…" />;
  if (error || !data) return <ErrorView message={error} />;

  const back = <BackLink to={`/class/${lessonId}`}>수업으로</BackLink>;
  if (!data.items || data.items.length === 0) {
    return (
      <div className="stack narrow-page">
        {back}
        <div className="card">
          <Empty icon={<ClipboardList size={26} />}>
            <strong>아직 확인 문제가 없어요</strong>
            <span className="small">선생님이 수업을 마치고 문제를 만들면 여기에서 풀 수 있어요.</span>
          </Empty>
        </div>
      </div>
    );
  }

  const items = data.items;
  const answered = items.filter((q) => picked[q.id]).length;
  const resultOf = (id: string) => result?.results.find((r) => r.questionId === id);

  async function submit() {
    setSubmitting(true);
    setSubmitError('');
    try {
      setResult(await api.submitQuiz(lessonId, items.map((q) => ({ questionId: q.id, answer: picked[q.id] ?? '' }))));
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (e) {
      setSubmitError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  function retry() {
    setResult(null);
    setPicked({});
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  return (
    <div className="stack narrow-page">
      {back}

      <div className="page-head">
        <div>
          <span className="eyebrow">확인 문제</span>
          <h2>배운 내용을 확인해요</h2>
        </div>
        <span className="chip chip-blue">
          {result ? `${result.score} / ${result.total} 맞힘` : `${answered} / ${items.length}`}
        </span>
      </div>
      <div className="progress" aria-hidden>
        <div style={{ width: `${((result ? result.total : answered) / items.length) * 100}%` }} />
      </div>

      {result && (
        <div className="hero-card row" style={{ gap: 16 }}>
          <PartyPopper size={34} />
          <div className="grow">
            <h3>다 풀었어요!</h3>
            <span className="muted-on-blue">
              {result.total}문제 중 {result.score}문제를 맞혔어요. 틀린 문제는 해설을 다시 읽어 봐요.
            </span>
          </div>
          <button className="btn btn-white btn-sm" onClick={retry}>
            <RotateCcw size={15} /> 다시 풀기
          </button>
        </div>
      )}

      {items.map((q, n) => {
        const choice = picked[q.id];
        const r = resultOf(q.id);
        const isOx = q.type === 'ox';
        return (
          <section key={q.id} className="card stack">
            <div className="row" style={{ alignItems: 'flex-start', gap: 12, flexWrap: 'nowrap' }}>
              <span className="q-number">{n + 1}</span>
              <p className="q-text">{q.question}</p>
            </div>
            <div className={`choices ${isOx ? 'ox' : ''}`}>
              {q.choices.map((c, i) => {
                const state = r
                  ? c === r.correctAnswer
                    ? 'correct'
                    : c === r.answer
                      ? 'wrong'
                      : ''
                  : c === choice
                    ? 'picked'
                    : '';
                return (
                  <button
                    key={i}
                    disabled={!!result}
                    aria-pressed={c === choice}
                    className={`choice ${state}`}
                    onClick={() => setPicked({ ...picked, [q.id]: c })}
                  >
                    {!isOx && <span className="letter">{letters[i]}</span>}
                    {c}
                  </button>
                );
              })}
            </div>
            {r && (
              <div className={`feedback ${r.correct ? 'ok' : 'hint'}`}>
                {r.correct ? <CheckCircle2 size={22} /> : <Lightbulb size={22} />}
                <div>
                  <strong>{r.correct ? '잘했어요!' : '괜찮아요, 같이 봐요.'}</strong>
                  <div>
                    {r.explanation}
                    {r.pageIndex && <span className="muted"> ({r.pageIndex}쪽)</span>}
                  </div>
                </div>
              </div>
            )}
          </section>
        );
      })}

      {!result && (
        <div className="stack-sm">
          {submitError && <p className="error-text center">{submitError}</p>}
          <button className="btn btn-primary btn-lg btn-block" onClick={submit} disabled={submitting || answered === 0}>
            <Send size={18} /> {submitting ? '채점하는 중…' : answered < items.length ? `제출하기 (${items.length - answered}문제 남음)` : '제출하기'}
          </button>
        </div>
      )}
    </div>
  );
}
