const useMock = (import.meta.env.VITE_USE_MOCK ?? 'true') === 'true';

export const config = {
  useMock,
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, ''),
  wsBaseUrl: (import.meta.env.VITE_WS_BASE_URL ?? 'ws://localhost:8000').replace(/\/$/, ''),
};

/**
 * 백엔드에 아직 없는 기능은 목 모드에서만 보여줌.
 * 백엔드에 API가 생기면 해당 값을 true로 바꾸고 api/index.ts에 연결하면 됩니다.
 */
export const features = {
  superschool: useMock, // 슈퍼스쿨 로그인·연동
  calendar: useMock, // 메인 화면 일정
  profileEdit: useMock, // 이름·이메일 수정, 프로필 사진, 비밀번호 변경
  explainTerm: useMock, // 단어를 넣으면 AI가 뜻 채우기
};
