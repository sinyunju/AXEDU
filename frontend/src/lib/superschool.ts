// 슈퍼스쿨 연동 흐름 (OAuth 방식 가정)
// 시작할 때 state를 만들어 두고, 돌아왔을 때 같은 state인지 확인합니다(다른 사이트가 끼어드는 것 방지).
import { api } from '../api';
import { randomId } from './id';
import type { Role } from '../api/types';

export type SuperschoolMode = 'login' | 'link';

interface Flow {
  state: string;
  mode: SuperschoolMode;
  returnTo?: string;
}

const KEY = 'superschool.flow';

/** 인증 페이지 주소를 만들고 흐름 정보를 저장. 앱 안 주소면 그대로 돌려줌(목 모드) */
export function beginSuperschool(mode: SuperschoolMode, opts: { role?: Role; returnTo?: string } = {}) {
  const state = randomId();
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ state, mode, returnTo: opts.returnTo } satisfies Flow));
  } catch {
    /* 저장 못 하면 돌아왔을 때 state 확인에서 실패 */
  }
  const base = api.superschoolAuthorizeUrl(mode, opts.role);
  return `${base}${base.includes('?') ? '&' : '?'}state=${encodeURIComponent(state)}`;
}

/** 돌아왔을 때 저장해 둔 흐름 꺼내기 (한 번만 쓸 수 있음) */
export function takeSuperschoolFlow(state: string | null): Flow | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    sessionStorage.removeItem(KEY);
    const flow = raw ? (JSON.parse(raw) as Flow) : null;
    return flow && state && flow.state === state ? flow : null;
  } catch {
    return null;
  }
}
