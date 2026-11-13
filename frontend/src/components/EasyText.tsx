// 쉬운 문장 안의 어려운 말을 하이라이트하고, 누르면 쉬운 뜻을 보여줍니다.
import { BookOpen } from 'lucide-react';
import { Fragment, useState } from 'react';
import type { Term } from '../api/types';

function escapeRegExp(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** size="sm": 자막 말풍선처럼 작은 글씨 */
export function EasyText({ text, terms, size = 'md' }: { text: string; terms: Term[]; size?: 'md' | 'sm' }) {
  const [open, setOpen] = useState<Term | null>(null);
  const valid = terms.filter((t) => t.word.trim());
  const cls = size === 'sm' ? 'easy-text easy-text-sm' : 'easy-text';

  if (valid.length === 0) return <p className={cls}>{text}</p>;

  // 긴 낱말부터 찾아야 "광합성량"이 "광합성"보다 먼저 잡힘
  const words = [...valid].sort((a, b) => b.word.length - a.word.length);
  const pattern = new RegExp(`(${words.map((t) => escapeRegExp(t.word)).join('|')})`, 'g');
  const parts = text.split(pattern);

  return (
    <div>
      <p className={cls}>
        {parts.map((part, i) => {
          const term = valid.find((t) => t.word === part);
          return term ? (
            <button
              key={i}
              className={`term ${open?.word === term.word ? 'open' : ''}`}
              aria-expanded={open?.word === term.word}
              onClick={() => setOpen(open?.word === term.word ? null : term)}
            >
              {part}
            </button>
          ) : (
            <Fragment key={i}>{part}</Fragment>
          );
        })}
      </p>
      {open && (
        <div className="term-card" role="status">
          <div className="term-icon">
            <BookOpen size={18} />
          </div>
          <div>
            <strong>{open.word}</strong>
            <span>{open.meaning}</span>
          </div>
        </div>
      )}
    </div>
  );
}
