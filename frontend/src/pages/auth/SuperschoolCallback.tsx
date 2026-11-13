// 슈퍼스쿨 인증을 마치고 돌아오는 곳: /auth/superschool/callback?code=…&state=…
import { AlertCircle } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../../api';
import { homeFor, useAuth } from '../../auth/AuthContext';
import { Loading } from '../../components/ui';
import { takeSuperschoolFlow } from '../../lib/superschool';

export function SuperschoolCallback() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { loginWithSuperschool, updateUser } = useAuth();
  const [error, setError] = useState('');
  const started = useRef(false); // StrictMode에서 두 번 실행 방지 (code는 한 번만 쓸 수 있음)

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const code = params.get('code');
    const flow = takeSuperschoolFlow(params.get('state'));
    if (params.get('error')) return setError('슈퍼스쿨에서 연결을 취소했어요.');
    if (!code || !flow) return setError('연결 정보가 맞지 않아요. 처음부터 다시 시도해 주세요.');

    (async () => {
      try {
        if (flow.mode === 'link') {
          updateUser(await api.linkSuperschool(code));
          navigate(flow.returnTo ?? '/settings?tab=links', { replace: true });
        } else {
          const user = await loginWithSuperschool(code);
          navigate(flow.returnTo ?? homeFor(user.role), { replace: true });
        }
      } catch (err) {
        setError((err as Error).message);
      }
    })();
  }, [params, navigate, loginWithSuperschool, updateUser]);

  if (!error) return <Loading label="슈퍼스쿨 계정을 확인하는 중…" />;

  return (
    <div className="auth-wrap">
      <div className="card auth-card stack center">
        <div className="empty-icon" style={{ margin: '0 auto', background: 'var(--bad-soft)', color: 'var(--bad)' }}>
          <AlertCircle size={26} />
        </div>
        <h3>연결하지 못했어요</h3>
        <p className="muted">{error}</p>
        <Link to="/login" className="btn btn-primary btn-block">
          로그인 화면으로
        </Link>
      </div>
    </div>
  );
}
