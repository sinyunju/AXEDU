// 요소 전체화면. Fullscreen API가 없는 브라우저(구형 iPad 등)는 화면을 꽉 채우는 CSS(.pseudo-fullscreen)로 대신합니다.
import { useCallback, useEffect, useState, type RefObject } from 'react';

/* eslint-disable @typescript-eslint/no-explicit-any */
const fsElement = () => document.fullscreenElement ?? (document as any).webkitFullscreenElement ?? null;

export function useFullscreen(ref: RefObject<HTMLElement | null>) {
  const [active, setActive] = useState(false);
  const [pseudo, setPseudo] = useState(false);

  useEffect(() => {
    const onChange = () => setActive(Boolean(ref.current) && fsElement() === ref.current);
    document.addEventListener('fullscreenchange', onChange);
    document.addEventListener('webkitfullscreenchange', onChange);
    return () => {
      document.removeEventListener('fullscreenchange', onChange);
      document.removeEventListener('webkitfullscreenchange', onChange);
    };
  }, [ref]);

  // 대체 모드에서는 Esc로 빠져나오기
  useEffect(() => {
    if (!pseudo) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setPseudo(false);
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [pseudo]);

  const enter = useCallback(async () => {
    const el: any = ref.current;
    if (!el) return;
    try {
      if (el.requestFullscreen) return await el.requestFullscreen();
      if (el.webkitRequestFullscreen) return el.webkitRequestFullscreen();
    } catch {
      /* 거부되면 대체 모드 */
    }
    setPseudo(true);
  }, [ref]);

  const exit = useCallback(() => {
    if (pseudo) return setPseudo(false);
    const d: any = document;
    if (fsElement()) (d.exitFullscreen ?? d.webkitExitFullscreen)?.call(d);
  }, [pseudo]);

  const on = active || pseudo;
  return { on, pseudo, enter, exit, toggle: on ? exit : enter };
}
