// 로그인 상태 (교사·학생 공용). 토큰은 탭 단위로 두고, 앱 시작 시 /auth/me로 확인합니다.
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { api } from '../api';
import { getToken, setToken } from '../api/token';
import type { AuthResponse, SignupInput, User } from '../api/types';

interface AuthState {
  user: User | null;
  ready: boolean; // 저장된 토큰 확인이 끝났는지
  login: (username: string, password: string) => Promise<User>;
  signup: (input: SignupInput) => Promise<User>;
  /** 슈퍼스쿨 인증 후 돌아온 code로 로그인 */
  loginWithSuperschool: (code: string) => Promise<User>;
  /** 프로필 수정·연동 변경 후 화면의 사용자 정보 갱신 */
  updateUser: (user: User) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      setReady(true);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setReady(true));
  }, []);

  const accept = useCallback((res: AuthResponse) => {
    setToken(res.token);
    setUser(res.user);
    return res.user;
  }, []);

  const login = useCallback(
    async (username: string, password: string) => accept(await api.login(username, password)),
    [accept],
  );
  const signup = useCallback(async (input: SignupInput) => accept(await api.signup(input)), [accept]);
  const loginWithSuperschool = useCallback(
    async (code: string) => accept(await api.superschoolLogin(code)),
    [accept],
  );

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, ready, login, signup, loginWithSuperschool, updateUser: setUser, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('AuthProvider 안에서만 사용할 수 있어요');
  return ctx;
}

/** 역할별 첫 화면 */
// eslint-disable-next-line react-refresh/only-export-components
export const homeFor = (role: User['role']) => (role === 'teacher' ? '/teacher' : '/student');

/** 선생님 이름 뒤 호칭 (이름에 이미 '선생님'이 있으면 생략) */
// eslint-disable-next-line react-refresh/only-export-components
export const displayName = (u: Pick<User, 'name' | 'role'>) =>
  u.role === 'teacher' && !u.name.endsWith('선생님') ? `${u.name} 선생님` : u.name;
