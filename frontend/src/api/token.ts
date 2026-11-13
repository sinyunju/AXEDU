// 토큰은 탭 단위(sessionStorage)로 저장합니다.
// - 한 브라우저에서 교사 탭과 학생 탭을 동시에 띄워 시험할 수 있고
// - 학교 공용 기기에서 탭을 닫으면 로그아웃됩니다.
const KEY = 'auth.token';

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) sessionStorage.setItem(KEY, token);
    else sessionStorage.removeItem(KEY);
  } catch {
    /* 무시 */
  }
}
