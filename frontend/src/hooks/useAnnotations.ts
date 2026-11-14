// 수업 자료 필기: 처음에 내 필기 전체를 불러오고, 바뀐 페이지는 잠시 뒤 서버에 저장합니다.
// - 같은 페이지를 연달아 고치면 마지막 것만 저장 (SAVE_DELAY_MS)
// - 화면을 떠날 때 남은 저장은 keepalive로 보냄
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { Stroke } from '../api/types';

const SAVE_DELAY_MS = 700;
const NONE: Stroke[] = [];

export type SaveState = 'idle' | 'saving' | 'saved' | 'error';

export function useAnnotations(lessonId: string | undefined) {
  const [pages, setPages] = useState<Record<number, Stroke[]>>({});
  const [saveState, setSaveState] = useState<SaveState>('idle');
  // 아직 저장 안 된 페이지. 키 `${lessonId}:${page}` (회차를 옮겨 가도 원래 회차로 저장되도록)
  const pending = useRef(new Map<string, { lessonId: string; page: number; strokes: Stroke[] }>());
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const flush = useCallback(async (keepalive = false) => {
    clearTimeout(timer.current);
    if (pending.current.size === 0) return;
    const batch = [...pending.current];
    pending.current.clear();
    setSaveState('saving');
    try {
      await Promise.all(batch.map(([, p]) => api.saveAnnotation(p.lessonId, p.page, p.strokes, keepalive)));
      setSaveState(pending.current.size ? 'saving' : 'saved');
    } catch {
      // 실패한 페이지는 다시 대기열에 (그 사이 새로 고친 게 있으면 그것을 우선)
      batch.forEach(([key, p]) => {
        if (!pending.current.has(key)) pending.current.set(key, p);
      });
      setSaveState('error');
      timer.current = setTimeout(() => void flush(), 5000);
    }
  }, []);

  useEffect(() => {
    if (!lessonId) return;
    let cancelled = false;
    setPages({});
    api
      .getAnnotations(lessonId)
      .then((loaded) => !cancelled && setPages((prev) => ({ ...loaded, ...prev }))) // 불러오는 사이 그린 것 우선
      .catch(() => {
        /* 불러오기 실패해도 새로 그리는 것은 가능 */
      });
    const onHide = () => void flush(true);
    window.addEventListener('pagehide', onHide);
    return () => {
      cancelled = true;
      window.removeEventListener('pagehide', onHide);
      void flush(true);
    };
  }, [lessonId, flush]);

  const setStrokes = useCallback(
    (page: number, strokes: Stroke[]) => {
      if (!lessonId) return;
      setPages((prev) => ({ ...prev, [page]: strokes }));
      pending.current.set(`${lessonId}:${page}`, { lessonId, page, strokes });
      setSaveState('saving');
      clearTimeout(timer.current);
      timer.current = setTimeout(() => void flush(), SAVE_DELAY_MS);
    },
    [lessonId, flush],
  );

  return { strokesOf: (page: number) => pages[page] ?? NONE, setStrokes, saveState };
}
