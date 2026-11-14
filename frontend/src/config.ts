const useMock = (import.meta.env.VITE_USE_MOCK ?? 'true') === 'true';

/**
 * 백엔드 주소. 값이 없거나 'auto'면 "지금 이 페이지를 연 주소의 8000번 포트"를 씀.
 * - PC에서 http://localhost:5173 → http://localhost:8000
 * - 아이패드에서 http://192.168.0.10:5173 → http://192.168.0.10:8000
 *   (와이파이가 바뀌어 PC의 IP가 달라져도 .env.local을 고칠 필요가 없음)
 * 배포(Vercel)할 때는 VITE_API_BASE_URL / VITE_WS_BASE_URL에 실제 백엔드 주소를 적어야 함.
 */
function backendUrl(value: string | undefined, kind: 'http' | 'ws') {
  if (value && value !== 'auto') return value.replace(/\/$/, '');
  const { protocol, hostname } = window.location;
  const secure = protocol === 'https:';
  const scheme = kind === 'http' ? (secure ? 'https' : 'http') : secure ? 'wss' : 'ws';
  return `${scheme}://${hostname}:8000`;
}

export const config = {
  useMock,
  apiBaseUrl: backendUrl(import.meta.env.VITE_API_BASE_URL, 'http'),
  wsBaseUrl: backendUrl(import.meta.env.VITE_WS_BASE_URL, 'ws'),
};

/**
 * 백엔드에 아직 없는 기능은 목 모드에서만 보여줌.
 * 백엔드에 API가 생기면 해당 값을 true로 바꾸고 api/index.ts에 연결하면 됩니다.
 */
export const features = {
  superschool: useMock, // 슈퍼스쿨 로그인·연동
  calendar: true, // 메인 화면 일정 (실서버는 회차의 수업 날짜만, 학사 일정은 슈퍼스쿨 연동 후)
  profileEdit: useMock, // 이름·이메일 수정, 프로필 사진, 비밀번호 변경
  explainTerm: useMock, // 단어를 넣으면 AI가 뜻 채우기
};
