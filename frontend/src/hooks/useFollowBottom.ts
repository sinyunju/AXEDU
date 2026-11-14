// 실시간으로 쌓이는 목록을 칸 안에서 스크롤할 때:
// - 새 항목이 오면 맨 아래로 따라 내려감
// - 학생이 위로 올려서 읽는 중이면 건드리지 않고 "새 설명 보기" 버튼만 띄움
// - 페이지(key)가 바뀌면 그 페이지의 맨 아래로
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';

const NEAR_BOTTOM_PX = 40;

export function useFollowBottom(key: unknown, count: number) {
  const ref = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const [hasNewBelow, setHasNewBelow] = useState(false);

  const toBottom = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    follow.current = true;
    setHasNewBelow(false);
  }, []);

  const onScroll = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight <= NEAR_BOTTOM_PX;
    follow.current = atBottom;
    if (atBottom) setHasNewBelow(false);
  }, []);

  // 페이지가 바뀌면 처음부터 따라가기
  useLayoutEffect(() => {
    follow.current = true;
    setHasNewBelow(false);
    toBottom();
  }, [key, toBottom]);

  useEffect(() => {
    if (count === 0) return;
    if (follow.current) toBottom();
    else setHasNewBelow(true);
  }, [count, toBottom]);

  return { ref, onScroll, hasNewBelow, toBottom };
}
