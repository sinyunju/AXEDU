import { ChevronDown, Link2, LogOut, Palette, Sprout, UserRound } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { displayName, homeFor, useAuth } from '../auth/AuthContext';
import { config, features } from '../config';
import { Avatar } from './Avatar';

function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // 바깥 클릭·Esc·페이지 이동 시 닫기
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);
  useEffect(() => setOpen(false), [location.pathname, location.search]);

  if (!user) return null;

  return (
    <div className="user-menu" ref={ref}>
      <button className="user-trigger" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <Avatar user={user} size={32} />
        <span className="user-name">{displayName(user)}</span>
        <ChevronDown size={16} className="muted" />
      </button>
      {open && (
        <div className="menu" role="menu">
          <div className="menu-head">
            <Avatar user={user} size={44} />
            <div>
              <strong>{displayName(user)}</strong>
              <div className="muted small">
                {user.role === 'teacher' ? '선생님' : '학생'} · @{user.username}
              </div>
            </div>
          </div>
          <Link role="menuitem" to="/settings?tab=profile" className="menu-item">
            <UserRound size={17} /> 내 정보
          </Link>
          <Link role="menuitem" to="/settings?tab=appearance" className="menu-item">
            <Palette size={17} /> 화면 테마
          </Link>
          {features.superschool && (
            <Link role="menuitem" to="/settings?tab=links" className="menu-item">
              <Link2 size={17} /> 계정 연동
              {user.superschoolLinked && <span className="chip chip-ok" style={{ marginLeft: 'auto', height: 22 }}>연결됨</span>}
            </Link>
          )}
          <div className="menu-sep" />
          <button
            role="menuitem"
            className="menu-item danger"
            onClick={() => {
              logout();
              navigate('/');
            }}
          >
            <LogOut size={17} /> 로그아웃
          </button>
        </div>
      )}
    </div>
  );
}

export function Layout() {
  const { user } = useAuth();

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-inner">
          <Link to={user ? homeFor(user.role) : '/'} className="brand">
            <span className="brand-mark">
              <Sprout size={19} strokeWidth={2.4} />
            </span>
            천천히
          </Link>
          {config.useMock && <span className="chip chip-warn">목 데이터</span>}
          <div className="topbar-user">
            <UserMenu />
          </div>
        </div>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
