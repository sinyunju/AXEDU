// 키보드로 페이지 넘기기: ←/↑/PageUp = 이전, →/↓/PageDown/Space = 다음.
// 발표용 리모컨(클리커)도 대부분 PageUp/PageDown을 보냅니다. 입력창·버튼에 초점이 있을 때는 무시.
import { useEffect, useRef } from 'react';

const PREV = new Set(['ArrowLeft', 'ArrowUp', 'PageUp']);
const NEXT = new Set(['ArrowRight', 'ArrowDown', 'PageDown', ' ']);

export function usePageKeys(enabled: boolean, onMove: (delta: -1 | 1) => void) {
  const cb = useRef(onMove);
  cb.current = onMove;
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey) return;
      if (t?.closest('input, textarea, select, [contenteditable="true"], [role="separator"]')) return;
      if (e.key === ' ' && t?.closest('button')) return;
      if (PREV.has(e.key)) {
        e.preventDefault();
        cb.current(-1);
      } else if (NEXT.has(e.key)) {
        e.preventDefault();
        cb.current(1);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [enabled]);
}
