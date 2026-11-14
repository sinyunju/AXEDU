// 실시간 쉬운 자막 목록 (교사·학생 공용)
// - content: 일반 말풍선
// - flow: 구분선 + 작은 글씨 ("지금부터 정리해요")
// - notice: 강조 상자 + "과제" 배지 (과제·준비물 안내)
import { ClipboardList, Presentation } from 'lucide-react';
import type { CaptionItem, Term } from '../api/types';
import { EasyText } from './EasyText';

export function CaptionList({ items, hardWords = [] }: { items: CaptionItem[]; hardWords?: Term[] }) {
  return (
    <ul className="captions">
      {items.map((c, i) =>
        c.kind === 'flow' ? (
          <li key={i} className="caption-flow">
            <span>{c.text}</span>
          </li>
        ) : c.kind === 'notice' ? (
          <li key={i} className="caption-notice">
            <span className="chip chip-warn notice-badge">
              <ClipboardList size={13} /> 과제
            </span>
            <EasyText text={c.text} terms={hardWords} size="sm" />
          </li>
        ) : (
          <li key={i} className="caption">
            <div className="who" aria-hidden>
              <Presentation size={16} />
            </div>
            <div className="bubble-body">
              <EasyText text={c.text} terms={hardWords} size="sm" />
            </div>
          </li>
        ),
      )}
    </ul>
  );
}
