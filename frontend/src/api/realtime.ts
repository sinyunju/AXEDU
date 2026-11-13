// 수업 중 실시간 채널.
// 실서버: WebSocket  /ws/lessons/{lessonId}?token=<access_token>  (백엔드 README "WebSocket")
//   - 접속(재접속) 즉시 서버가 teacher_page → (있으면) page_update → (끝난 수업이면) lesson_ended 를 보냄
//   - 4401(로그인 필요)/4403(권한 없음)/4404(회차 없음)으로 닫히면 재연결하지 않고 rejected로 알림
//   - 25초마다 ping
// 목 모드: BroadcastChannel로 같은 브라우저의 교사 탭 ↔ 학생 탭을 연결
import { config } from '../config';
import { MOCK_KEYS, mockApi } from './mock';
import { getToken } from './token';
import type { CaptionItem, ServerMessage, TeacherMessage, Term } from './types';

export type Role = 'teacher' | 'student';

export interface LiveChannel {
  send(msg: TeacherMessage): void;
  close(): void;
}

const PING_MS = 25_000;
const RETRY_MS = 1_500;
const FATAL_CODES: Record<number, string> = {
  4401: '로그인이 필요해요. 다시 로그인해 주세요',
  4403: '이 수업에 들어갈 권한이 없어요',
  4404: '수업을 찾을 수 없어요. 아직 공개되지 않았을 수 있어요',
};

export function connectLive(lessonId: string, role: Role, onMessage: (msg: ServerMessage) => void): LiveChannel {
  return config.useMock ? connectMock(lessonId, role, onMessage) : connectWs(lessonId, onMessage);
}

// ---------- 실서버 ----------

/** 서버 메시지(page_no, easy_transcript, type) → 화면 형식 */
type RawCaption = { text: string; type: 'content' | 'flow' | 'notice' };
type RawServerMessage =
  | { type: 'teacher_page'; page_no: number }
  | { type: 'page_update'; page_no: number; easy_transcript: RawCaption[]; hard_words: Term[] }
  | { type: 'lesson_started'; page_no: number }
  | { type: 'lesson_ended' }
  | { type: 'ack'; for: 'transcript' | 'page_change'; page_no: number; ignored?: boolean }
  | { type: 'error'; detail: string }
  | { type: 'pong' };

function fromServer(raw: RawServerMessage): ServerMessage | null {
  switch (raw.type) {
    case 'teacher_page':
      return { type: 'teacher_page', pageIndex: raw.page_no };
    case 'page_update':
      return {
        type: 'page_update',
        pageIndex: raw.page_no,
        captions: {
          items: (raw.easy_transcript ?? []).map((c): CaptionItem => ({ text: c.text, kind: c.type ?? 'content' })),
          hardWords: raw.hard_words ?? [],
        },
      };
    case 'lesson_started':
      return { type: 'lesson_started', pageIndex: raw.page_no };
    case 'lesson_ended':
      return { type: 'lesson_ended' };
    case 'ack':
      return { type: 'ack', for: raw.for, pageIndex: raw.page_no, ignored: raw.ignored };
    case 'error':
      return { type: 'error', detail: raw.detail };
    default:
      return null; // pong 등
  }
}

function toServer(msg: TeacherMessage) {
  return msg.type === 'page_change'
    ? { type: 'page_change', page_no: msg.pageIndex }
    : { type: 'transcript', page_no: msg.pageIndex, text: msg.text, final: true }; // 확정된 문장만 보냄
}

function connectWs(lessonId: string, onMessage: (msg: ServerMessage) => void): LiveChannel {
  let ws: WebSocket | null = null;
  let closed = false;
  let ping: ReturnType<typeof setInterval> | undefined;
  let retry: ReturnType<typeof setTimeout> | undefined;
  const queue: TeacherMessage[] = [];

  const open = () => {
    const token = getToken();
    if (!token) {
      onMessage({ type: 'rejected', code: 4401, reason: FATAL_CODES[4401] });
      return;
    }
    ws = new WebSocket(`${config.wsBaseUrl}/ws/lessons/${lessonId}?token=${encodeURIComponent(token)}`);
    ws.onopen = () => {
      queue.splice(0).forEach((m) => ws?.send(JSON.stringify(toServer(m))));
      ping = setInterval(() => ws?.readyState === WebSocket.OPEN && ws.send(JSON.stringify({ type: 'ping' })), PING_MS);
    };
    ws.onmessage = (e) => {
      try {
        const msg = fromServer(JSON.parse(e.data) as RawServerMessage);
        if (msg) onMessage(msg);
      } catch {
        /* 알 수 없는 메시지는 무시 */
      }
    };
    ws.onclose = (e) => {
      clearInterval(ping);
      if (closed) return;
      if (FATAL_CODES[e.code]) {
        closed = true; // 권한·로그인 문제는 다시 붙어도 같으므로 중단
        onMessage({ type: 'rejected', code: e.code, reason: FATAL_CODES[e.code] });
        return;
      }
      retry = setTimeout(open, RETRY_MS); // 그 밖의 끊김은 재연결
    };
  };
  open();

  return {
    send(msg) {
      if (msg.type === 'transcript' && !msg.text.trim()) return;
      if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(toServer(msg)));
      else queue.push(msg);
    },
    close() {
      closed = true;
      clearInterval(ping);
      clearTimeout(retry);
      ws?.close();
    },
  };
}

// ---------- 목 모드 ----------

function connectMock(lessonId: string, role: Role, onMessage: (msg: ServerMessage) => void): LiveChannel {
  const bc = new BroadcastChannel(`live:${lessonId}`);
  bc.onmessage = (e) => onMessage(e.data as ServerMessage);
  const pageKey = `${MOCK_KEYS.teacherPage}.${lessonId}`;

  // 실서버처럼 접속 즉시 선생님 위치를 알려 줌
  try {
    const saved = Number(localStorage.getItem(pageKey));
    if (saved > 0 && role === 'student') setTimeout(() => onMessage({ type: 'teacher_page', pageIndex: saved }), 0);
  } catch {
    /* 무시 */
  }

  const broadcast = (msg: ServerMessage) => {
    bc.postMessage(msg);
    onMessage(msg); // 같은 탭에도 반영
  };

  return {
    send(msg) {
      if (msg.type === 'page_change') {
        try {
          localStorage.setItem(pageKey, String(msg.pageIndex));
        } catch {
          /* 무시 */
        }
        broadcast({ type: 'teacher_page', pageIndex: msg.pageIndex });
        return;
      }
      if (!msg.text.trim()) return;
      const captions = mockApi.addTranscript(lessonId, msg.pageIndex, msg.text);
      if (!captions) {
        onMessage({ type: 'error', detail: '수업이 진행 중이 아닙니다. 수업을 시작해 주세요' });
        return;
      }
      setTimeout(() => broadcast({ type: 'page_update', pageIndex: msg.pageIndex, captions }), 500);
    },
    close() {
      bc.close();
    },
  };
}
