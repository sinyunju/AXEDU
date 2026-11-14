// 수업 중 실시간 상태 (교사·학생 공용)
// - 자막은 페이지별로 보관하고, page_update가 오면 그 페이지를 통째로 교체
// - 처음 보는 페이지는 GET /lessons/{id}/pages/{n}으로 지금까지의 자막을 불러옴
// - 4401로 거부되면 로그아웃 후 로그인 화면으로
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import { connectLive, type LiveChannel } from '../api/realtime';
import type { LessonStatus, PageCaptions, PointerPos, TeacherMessage } from '../api/types';
import { useAuth } from '../auth/AuthContext';

const EMPTY: PageCaptions = { items: [], hardWords: [] };

export function useLiveLesson(lessonId: string | undefined, role: 'teacher' | 'student') {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [captions, setCaptions] = useState<Record<number, PageCaptions>>({});
  const [teacherPage, setTeacherPage] = useState<number | null>(null);
  const [liveStatus, setLiveStatus] = useState<LessonStatus | null>(null); // lesson_started/ended로 바뀜
  const [serverError, setServerError] = useState<string | null>(null);
  const [rejected, setRejected] = useState<string | null>(null);
  const [pointer, setPointer] = useState<{ pageIndex: number; pos: PointerPos } | null>(null); // 선생님 레이저
  const channel = useRef<LiveChannel | null>(null);
  const loaded = useRef(new Set<number>());

  useEffect(() => {
    if (!lessonId) return;
    loaded.current = new Set();
    setCaptions({});
    const ch = connectLive(lessonId, role, (msg) => {
      switch (msg.type) {
        case 'teacher_page':
          setTeacherPage(msg.pageIndex);
          setPointer(null);
          break;
        case 'pointer':
          setPointer(msg.pos ? { pageIndex: msg.pageIndex, pos: msg.pos } : null);
          break;
        case 'page_update':
          loaded.current.add(msg.pageIndex);
          setCaptions((prev) => ({ ...prev, [msg.pageIndex]: msg.captions }));
          break;
        case 'lesson_started':
          setLiveStatus('live');
          setTeacherPage(msg.pageIndex);
          break;
        case 'lesson_ended':
          setLiveStatus('ended');
          setPointer(null);
          break;
        case 'error':
          setServerError(msg.detail);
          break;
        case 'ack':
          setServerError(null);
          break;
        case 'rejected':
          setRejected(msg.reason);
          if (msg.code === 4401) {
            logout();
            navigate('/login', { replace: true });
          }
          break;
      }
    });
    channel.current = ch;
    return () => ch.close();
  }, [lessonId, role, logout, navigate]);

  /** 이 페이지의 지금까지 자막을 한 번 불러옴 (이미 받았으면 생략) */
  const loadPage = useCallback(
    async (pageIndex: number) => {
      if (!lessonId || loaded.current.has(pageIndex)) return;
      loaded.current.add(pageIndex);
      try {
        const view = await api.getPageView(lessonId, pageIndex);
        setCaptions((prev) => (prev[pageIndex] ? prev : { ...prev, [pageIndex]: view }));
        setTeacherPage((prev) => prev ?? view.teacherPage);
      } catch {
        loaded.current.delete(pageIndex); // 다음에 다시 시도
      }
    },
    [lessonId],
  );

  const send = useCallback((msg: TeacherMessage) => channel.current?.send(msg), []);

  return {
    captionsOf: (pageIndex: number) => captions[pageIndex] ?? EMPTY,
    countOf: (pageIndex: number) => captions[pageIndex]?.items.length ?? 0,
    loadPage,
    teacherPage,
    /** 선생님 레이저 위치 (그 페이지를 보고 있을 때만), 없으면 null */
    pointerOn: (pageIndex: number): PointerPos => (pointer?.pageIndex === pageIndex ? pointer.pos : null),
    liveStatus,
    setLiveStatus,
    serverError,
    rejected,
    send,
  };
}
