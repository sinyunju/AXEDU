// 화면 보호: 로그인 안 했으면 로그인 화면으로, 역할이 다르면 그 역할의 첫 화면으로 보냄.
// role을 안 주면 로그인만 확인 (설정 화면처럼 교사·학생 공용)
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import type { Role } from '../api/types';
import { Loading } from '../components/ui';
import { homeFor, useAuth } from './AuthContext';

export function RequireRole({ role }: { role?: Role }) {
  const { user, ready } = useAuth();
  const location = useLocation();

  if (!ready) return <Loading label="확인 중…" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname, role }} />;
  if (role && user.role !== role) return <Navigate to={homeFor(user.role)} replace />;
  return <Outlet />;
}
