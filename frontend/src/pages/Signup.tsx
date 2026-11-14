// 회원가입 (학생 / 선생님 선택). 가입하면 바로 로그인되어 역할별 첫 화면으로 이동
import { GraduationCap, Presentation } from 'lucide-react';
import { TurtleMark } from '../components/TurtleMark';
import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import type { Role } from '../api/types';
import { homeFor, useAuth } from '../auth/AuthContext';
import { Segmented } from '../components/Segmented';
import { SuperschoolButton } from '../components/SuperschoolButton';
import { features } from '../config';

const roles: { value: Role; label: string; icon: typeof GraduationCap }[] = [
  { value: 'student', label: '학생', icon: GraduationCap },
  { value: 'teacher', label: '선생님', icon: Presentation },
];
const USERNAME_RULE = /^[A-Za-z0-9_.-]{3,32}$/;

export function Signup() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const initialRole = (useLocation().state as { role?: Role } | null)?.role ?? 'student';

  const [role, setRole] = useState<Role>(initialRole);
  const [name, setName] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const usernameInvalid = username.length > 0 && !USERNAME_RULE.test(username);
  const mismatch = confirm.length > 0 && password !== confirm;
  const roleLabel = roles.find((r) => r.value === role)!.label;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    if (!USERNAME_RULE.test(username)) return setError('아이디는 영문·숫자·_.- 3~32자로 만들어 주세요');
    if (password.length < 8) return setError('비밀번호는 8자 이상이어야 해요');
    if (password !== confirm) return setError('비밀번호가 서로 달라요');

    setBusy(true);
    try {
      const user = await signup({ role, name: name.trim(), username, password });
      navigate(homeFor(user.role), { replace: true });
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
          <h2>토끼와 거북이에 오신 걸 환영해요</h2>
        </div>

        <Segmented ariaLabel="가입 유형" kind="radio" options={roles} value={role} onChange={setRole} />

        {features.superschool && (
          <>
            <SuperschoolButton
              mode="login"
              role={role}
              label={`슈퍼스쿨 계정으로 ${roleLabel} 가입하기`}
              className="btn-lg btn-block"
            />
            <div className="or">또는 아이디로 가입</div>
          </>
        )}

        <label className="field">
          <span>이름</span>
          <input
            className="input"
            placeholder={role === 'teacher' ? '예: 김선생' : '예: 지우'}
            autoComplete="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </label>
        <label className="field">
          <span>아이디</span>
          <input
            className="input"
            placeholder="영문·숫자 3~32자"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value.trim())}
            aria-invalid={usernameInvalid}
            required
          />
          {usernameInvalid && <small className="error-text">영문·숫자·_.- 3~32자로 만들어 주세요</small>}
        </label>
        <label className="field">
          <span>비밀번호</span>
          <input
            className="input"
            type="password"
            placeholder="8자 이상"
            autoComplete="new-password"
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        <label className="field">
          <span>비밀번호 확인</span>
          <input
            className="input"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            aria-invalid={mismatch}
            required
          />
          {mismatch && <small className="error-text">비밀번호가 서로 달라요</small>}
        </label>

        {error && <p className="error-text">{error}</p>}
        <button className="btn btn-primary btn-lg btn-block" disabled={busy}>
          {busy ? '잠시만요…' : `${roleLabel}으로 가입하기`}
        </button>
        <p className="center muted small">
          이미 계정이 있나요?{' '}
          <Link to="/login">
            <strong>로그인</strong>
          </Link>
        </p>
      </form>
    </div>
  );
}
