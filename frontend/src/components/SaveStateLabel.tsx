import type { SaveState } from '../hooks/useAnnotations';

const TEXT: Record<SaveState, string> = { idle: '', saving: '저장 중…', saved: '필기 저장됨', error: '저장 실패 · 다시 시도 중' };

export function SaveStateLabel({ state }: { state: SaveState }) {
  if (state === 'idle') return null;
  return (
    <span className={`save-state ${state === 'error' ? 'error' : ''}`} role="status">
      {TEXT[state]}
    </span>
  );
}
