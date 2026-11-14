// 로그인 (교사·학생 공용. 계정의 역할에 따라 첫 화면이 달라짐)
import { TurtleMark } from '../components/TurtleMark';
import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import type { Role } from '../api/types';
import { homeFor, useAuth } from '../auth/AuthContext';
import { SuperschoolButton } from '../components/SuperschoolButton';
import { config, features } from '../config';

export function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const state = useLocation().state as { from?: string; role?: Role } | null;

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const user = await login(username, password);
      // 보호된 화면에서 왔고 역할이 맞으면 그 화면으로, 아니면 역할별 첫 화면으로
      const back = state?.from && (!state.role || state.role === user.role) ? state.from : homeFor(user.role);
      navigate(back, { replace: true });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <form className="card auth-card stack" onSubmit={onSubmit}>
        <div className="auth-head">
          <span className="brand-mark">
            <TurtleMark size={30} />
          </span>
          <h2>다시 만나서 반가워요</h2>
          <p className="muted">아이디와 비밀번호로 로그인해 주세요</p>
        </div>

        <label className="field">
          <span>아이디</span>
          <input
            className="input"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value.trim())}
            required
          />
        </label>
        <label className="field">
          <span>비밀번호</span>
          <input
            className="input"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>

        {error && <p className="error-text">{error}</p>}
        <button className="btn btn-primary btn-lg btn-block" disabled={busy}>
          {busy ? '잠시만요…' : '로그인'}
        </button>
        {features.superschool && (
          <>
            <div className="or">또는</div>
            <SuperschoolButton mode="login" role={state?.role} returnTo={state?.from} className="btn-lg btn-block" />
          </>
        )}
        <p className="center muted small">
          계정이 없나요?{' '}
          <Link to="/signup" state={{ role: state?.role }}>
            <strong>회원가입</strong>
          </Link>
        </p>
        {config.useMock && (
          <div className="hint-box">
            목 모드 데모 계정
            <br />
            선생님 <strong>teacher1</strong> · 학생 <strong>student1</strong>~<strong>3</strong> / 비밀번호 <strong>pass1234</strong>
          </div>
        )}
      </form>
    </div>
  );
}
