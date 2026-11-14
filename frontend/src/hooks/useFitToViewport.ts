// 요소 높이를 "화면에서 그 요소 윗변부터 아래 끝까지"로 맞춤 (스크롤하면 다시 계산).
// sticky 패널이 처음에는 아래쪽에서 시작해 화면 밖으로 넘치는 것을 막는다.
// enabled가 false면(휴대폰 폭·전체화면) 높이를 CSS에 맡긴다.
import { useEffect, type RefObject } from 'react';

export function useFitToViewport(ref: RefObject<HTMLElement | null>, enabled: boolean, gap = 16, minTop = 84) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!enabled) {
      el.style.height = '';
      return;
    }
    const mq = window.matchMedia('(min-width: 861px)');
    let frame = 0;
    const fit = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (!mq.matches) {
          el.style.height = '';
          return;
        }
        const top = Math.max(el.getBoundingClientRect().top, minTop);
        el.style.height = `${Math.max(320, window.innerHeight - top - gap)}px`;
      });
    };
    fit();
    window.addEventListener('scroll', fit, { passive: true });
    window.addEventListener('resize', fit);
    mq.addEventListener('change', fit);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('scroll', fit);
      window.removeEventListener('resize', fit);
      mq.removeEventListener('change', fit);
      el.style.height = '';
    };
  }, [ref, enabled, gap, minTop]);
}
