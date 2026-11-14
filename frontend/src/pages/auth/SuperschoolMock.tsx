// 개발용 슈퍼스쿨 인증 화면 (프론트 목 모드, 또는 백엔드 SUPERSCHOOL_MOCK=true일 때).
// 실제 슈퍼스쿨 화면을 흉내 내지 않고, 개발용이라는 것을 분명히 표시합니다.
import { FlaskConical, GraduationCap, Presentation } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';

export function SuperschoolMock() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const mode = params.get('mode') === 'link' ? 'link' : 'login';
  const state = params.get('state') ?? '';
  const role = params.get('role');

  const finish = (code: string) =>
    navigate(`/auth/superschool/callback?${new URLSearchParams({ code, state })}`, { replace: true });
  const cancel = () => navigate(`/auth/superschool/callback?${new URLSearchParams({ error: 'access_denied', state })}`, { replace: true });

  return (
    <div className="auth-wrap">
      <div className="card auth-card stack">
        <div className="auth-head">
          <div className="empty-icon">
            <FlaskConical size={26} />
          </div>
          <h3>개발용 연동 화면</h3>
          <p className="muted small">
            지금은 실제 슈퍼스쿨에 접속하지 않아요. 슈퍼스쿨 API를 연결하면 이 자리에 슈퍼스쿨 로그인·동의 화면이 나와요.
          </p>
        </div>

        {mode === 'login' ? (
          <>
            <p className="small">어떤 계정으로 로그인한 것처럼 할까요?</p>
            {role !== 'teacher' && (
              <button className="btn btn-primary btn-lg btn-block" onClick={() => finish('mock:student')}>
                <GraduationCap size={18} /> 학생 계정 (지우)
              </button>
            )}
            {role !== 'student' && (
              <button className="btn btn-lg btn-block" onClick={() => finish('mock:teacher')}>
                <Presentation size={18} /> 선생님 계정 (김하늘)
              </button>
            )}
          </>
        ) : (
          <>
            <p className="small">지금 로그인한 계정에 슈퍼스쿨을 연결하고 학사 일정·소속 정보를 가져와요.</p>
            <button className="btn btn-primary btn-lg btn-block" onClick={() => finish('mock:link')}>
              연결 허용
            </button>
          </>
        )}
        <button className="btn btn-ghost btn-block" onClick={cancel}>
          취소
        </button>
      </div>
    </div>
  );
}
