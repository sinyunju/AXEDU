// 수업 후(학생): 수업 범위 안에서만 답하는 챗봇. 이전 대화도 불러옴
import { Bot, Send } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../../api';
import type { ChatMessage } from '../../api/types';
import { BackLink } from '../../components/ui';
import { useAsync } from '../../hooks/useAsync';

const GREETING: ChatMessage = { from: 'bot', text: '이 수업에서 궁금한 걸 물어보세요. 배운 내용 안에서 쉽게 알려 줄게요.' };

export function Chat() {
  const { lessonId = '' } = useParams();
  const { data: lesson } = useAsync(() => api.getLesson(lessonId), [lessonId]);
  const [msgs, setMsgs] = useState<ChatMessage[]>([GREETING]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .getChatHistory(lessonId)
      .then((history) => setMsgs([GREETING, ...history]))
      .catch(() => {
        /* 기록을 못 불러와도 새로 물어볼 수 있음 */
      });
  }, [lessonId]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' });
  }, [msgs, busy]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const q = input.trim();
    if (!q || !lesson) return;
    setInput('');
    setError('');
    setMsgs((m) => [...m, { from: 'me', text: q }]);
    setBusy(true);
    try {
      const r = await api.askChat(lesson.id, q);
      setMsgs((m) => [...m, { from: 'bot', text: r.answer, relatedPage: r.relatedPage }]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack narrow-page">
      <BackLink to={`/class/${lessonId}`}>수업으로</BackLink>

      <div className="page-head">
        <div>
          <span className="eyebrow">{lesson && `${lesson.sessionNo}회차 · ${lesson.title}`}</span>
          <h2>궁금한 점 물어보기</h2>
        </div>
      </div>

      <section className="card chat-card">
        <div className="chat-log" ref={logRef}>
          {msgs.map((m, i) => (
            <div key={i} className={`msg ${m.from}`}>
              {m.from === 'bot' && (
                <div className="who" aria-hidden>
                  <Bot size={18} />
                </div>
              )}
              <div className="body">
                {m.text}
                {m.relatedPage && (
                  <div className="refs">
                    <Link to={`/class/${lessonId}`} className="chip chip-blue">
                      관련: {m.relatedPage}쪽
                    </Link>
                  </div>
                )}
              </div>
            </div>
          ))}
          {busy && (
            <div className="msg bot">
              <div className="who" aria-hidden>
                <Bot size={18} />
              </div>
              <div className="body">
                <span className="typing" aria-label="답을 만드는 중">
                  <i />
                  <i />
                  <i />
                </span>
              </div>
            </div>
          )}
          {error && <p className="error-text center small">{error}</p>}
        </div>
        <div className="chat-foot">
          <form className="composer" onSubmit={onSubmit}>
            <input value={input} maxLength={500} onChange={(e) => setInput(e.target.value)} placeholder="질문을 적어 주세요" />
            <button className="btn btn-primary btn-icon" aria-label="보내기" disabled={busy || !lesson || !input.trim()}>
              <Send size={17} />
            </button>
          </form>
        </div>
      </section>
    </div>
  );
}
