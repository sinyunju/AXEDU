// 집중 도우미 (학생 수업 화면)
// 웹캠으로 아래 상황이 일정 시간 이어지면 "집중!" 알림을 띄움. 학생 화면에만 보이고 선생님·서버로는 아무것도 보내지 않음.
//  - away   : 고개를 돌리거나 화면 밖을 봄
//  - noFace : 얼굴이 안 보임 (자리를 비움)
//  - closed : 눈을 감음
//  - still  : 눈동자가 거의 안 움직임 (멍하니 있음. 글을 읽을 때는 눈이 계속 움직여서 걸리지 않음)
// 다시 화면을 보고 1.5초 지나면 알림이 저절로 닫힘. "다시 집중할게요" 버튼으로도 닫을 수 있음.
//
// 시연 영상용: 주소에 ?focusDemo=1 을 붙이면 기준 시간이 짧아짐(3초·3초·6초), Shift+F로 알림을 바로 띄움
import { useCallback, useEffect, useRef, useState } from 'react';
// MediaPipe는 크기가 커서, 집중 도우미를 켤 때만 불러옴 (import('../lib/focusDetector'))

export type FocusReason = 'away' | 'noFace' | 'closed' | 'still';
export type FocusStatus = 'off' | 'starting' | 'watching' | 'error';

const NORMAL = { away: 8000, noFace: 8000, closed: 8000, still: 20000 };
const DEMO = { away: 3000, noFace: 3000, closed: 3000, still: 6000 };
const STILL_RANGE = 0.035; // 이 시간 동안 눈동자가 움직인 폭이 이보다 작으면 "멍하니"
const RECOVER_MS = 1500; // 다시 화면을 이만큼 보면 알림 닫힘
const COOLDOWN_MS = 4000; // 닫은 뒤 바로 다시 뜨지 않게
const FRAME_MS = 120; // 초당 약 8번 분석

function isDemo() {
  try {
    return new URLSearchParams(window.location.search).has('focusDemo') || localStorage.getItem('focus.demo') === '1';
  } catch {
    return false;
  }
}

export function useFocusGuard() {
  const [status, setStatus] = useState<FocusStatus>('off');
  const [error, setError] = useState('');
  const [alert, setAlert] = useState<FocusReason | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const alertRef = useRef<FocusReason | null>(null);
  const t = useRef({
    awaySince: 0,
    noFaceSince: 0,
    closedSince: 0,
    okSince: 0,
    cooldownUntil: 0,
    iris: [] as { t: number; x: number; y: number }[],
  });
  const limits = useRef(isDemo() ? DEMO : NORMAL);

  const show = useCallback((reason: FocusReason | null) => {
    if (alertRef.current === reason) return;
    alertRef.current = reason;
    setAlert(reason);
  }, []);

  const resetTimers = useCallback(() => {
    const s = t.current;
    s.awaySince = s.noFaceSince = s.closedSince = s.okSince = 0;
    s.iris = [];
  }, []);

  const stop = useCallback(() => {
    clearInterval(timer.current);
    stream.current?.getTracks().forEach((tr) => tr.stop()); // 카메라 끄기
    stream.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    resetTimers();
    show(null);
    setStatus('off');
  }, [resetTimers, show]);

  const start = useCallback(async () => {
    setError('');
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setError('카메라는 https 주소나 localhost에서만 켤 수 있어요.');
      setStatus('error');
      return;
    }
    setStatus('starting');
    try {
      const { analyzeFace, loadFaceLandmarker } = await import('../lib/focusDetector');
      const [landmarker, media] = await Promise.all([
        loadFaceLandmarker(),
        navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: 640, height: 480 }, audio: false }),
      ]);
      stream.current = media;
      const video = videoRef.current;
      if (!video) throw new Error('video element missing');
      video.srcObject = media;
      await video.play();
      resetTimers();
      limits.current = isDemo() ? DEMO : NORMAL;
      setStatus('watching');

      timer.current = setInterval(() => {
        if (!video.videoWidth || video.readyState < 2) return;
        const now = performance.now();
        const f = analyzeFace(landmarker.detectForVideo(video, now));
        const s = t.current;
        const L = limits.current;

        const since = (cond: boolean, prev: number) => (cond ? prev || now : 0);
        s.noFaceSince = since(!f.face, s.noFaceSince);
        s.awaySince = since(f.face && f.away, s.awaySince);
        s.closedSince = since(f.face && !f.away && f.closed, s.closedSince);
        const attentive = f.face && !f.away && !f.closed;

        // 눈동자 움직임 기록 (화면을 보고 있을 때만)
        if (attentive && f.iris) s.iris.push({ t: now, x: f.iris[0], y: f.iris[1] });
        else s.iris = [];
        s.iris = s.iris.filter((p) => now - p.t <= L.still);
        const range = (from: number) => {
          const pts = s.iris.filter((p) => p.t >= from);
          if (pts.length < 2) return 1;
          const xs = pts.map((p) => p.x);
          const ys = pts.map((p) => p.y);
          return Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
        };
        const covered = s.iris.length > 0 && now - s.iris[0].t >= L.still * 0.95;
        const still = covered && range(now - L.still) < STILL_RANGE;

        const current = alertRef.current;
        if (current) {
          // 알림 중: 다시 화면을 보고(멍한 경우엔 눈도 움직이고) 잠시 지나면 닫힘
          const recovered = attentive && (current !== 'still' || range(now - RECOVER_MS) >= STILL_RANGE);
          s.okSince = recovered ? s.okSince || now : 0;
          if (s.okSince && now - s.okSince >= RECOVER_MS) {
            show(null);
            resetTimers();
            s.cooldownUntil = now + COOLDOWN_MS;
          }
          return;
        }
        if (now < s.cooldownUntil) return;
        if (s.noFaceSince && now - s.noFaceSince >= L.noFace) show('noFace');
        else if (s.awaySince && now - s.awaySince >= L.away) show('away');
        else if (s.closedSince && now - s.closedSince >= L.closed) show('closed');
        else if (still) show('still');
      }, FRAME_MS);
    } catch (e) {
      const name = (e as DOMException)?.name;
      stop();
      setError(
        name === 'NotAllowedError'
          ? '카메라 사용이 허용되지 않았어요. 주소창의 자물쇠 아이콘에서 카메라를 허용해 주세요.'
          : name === 'NotFoundError'
            ? '카메라를 찾을 수 없어요.'
            : '집중 도우미를 켜지 못했어요. 인터넷 연결을 확인하고 다시 켜 주세요.',
      );
      setStatus('error');
    }
  }, [resetTimers, show, stop]);

  /** "다시 집중할게요" */
  const dismiss = useCallback(() => {
    show(null);
    resetTimers();
    t.current.cooldownUntil = performance.now() + COOLDOWN_MS;
  }, [resetTimers, show]);

  // 시연용: Shift+F로 알림 바로 띄우기 (집중 도우미가 켜져 있을 때)
  useEffect(() => {
    if (status !== 'watching') return;
    const onKey = (e: KeyboardEvent) => {
      if (e.shiftKey && (e.key === 'F' || e.key === 'f') && !(e.target as HTMLElement)?.closest?.('input, textarea')) {
        e.preventDefault();
        show('away');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [status, show]);

  // 화면을 떠나면 카메라 끄기
  useEffect(() => stop, [stop]);

  return { status, error, alert, start, stop, dismiss, videoRef, demo: limits.current === DEMO };
}
