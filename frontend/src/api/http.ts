import { config } from '../config';
import { getToken } from './token';

/** 백엔드 오류. message는 화면에 그대로 보여줄 문장 (백엔드 {detail}에서 꺼냄) */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** {detail: "..."} 또는 입력 검증 오류 {detail: [{msg}, ...]} 에서 사람이 읽을 문장만 꺼냄 */
function detailMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (typeof d === 'object' && d && 'msg' in d ? String((d as { msg: unknown }).msg) : ''))
      .filter(Boolean)
      .map((m) => m.replace(/^Value error, /, ''));
    if (msgs.length) return msgs.join(' / ');
  }
  if (status >= 500) return '서버에 문제가 생겼어요. 잠시 후 다시 시도해 주세요';
  return `요청을 처리하지 못했어요 (${status})`;
}

export async function http<T>(path: string, init?: RequestInit & { token?: string }): Promise<T> {
  const isForm = init?.body instanceof FormData;
  const token = init?.token ?? getToken();
  let res: Response;
  try {
    res = await fetch(`${config.apiBaseUrl}${path}`, {
      ...init,
      headers: {
        ...(isForm || !init?.body ? {} : { 'Content-Type': 'application/json' }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(0, '서버에 연결할 수 없어요. 인터넷과 서버 주소를 확인해 주세요');
  }

  const text = await res.text();
  let body: unknown = undefined;
  try {
    body = text ? JSON.parse(text) : undefined;
  } catch {
    body = undefined;
  }
  if (!res.ok) throw new ApiError(res.status, detailMessage(body, res.status));
  return body as T;
}

/** 백엔드가 주는 /files/... 상대 경로를 전체 주소로 */
export function fileUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined;
  if (/^(https?:|data:|blob:)/.test(path)) return path;
  return `${config.apiBaseUrl}${path.startsWith('/') ? '' : '/'}${path}`;
}
