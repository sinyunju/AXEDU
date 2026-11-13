// 계정 연동: 슈퍼스쿨 연결 / 해제
import { CalendarDays, CheckCircle2, School, Unlink, UserRound } from 'lucide-react';
import { useState } from 'react';
import { api } from '../../api';
import { useAuth } from '../../auth/AuthContext';
import { SuperschoolButton } from '../../components/SuperschoolButton';

export function LinksTab() {
  const { user, updateUser } = useAuth();
  const [busy, setBusy] = useState(false);

  if (!user) return null;

  async function unlink() {
    if (!window.confirm('슈퍼스쿨 연결을 해제할까요? 학사 일정이 메인 화면에서 사라져요.')) return;
    setBusy(true);
    try {
      updateUser(await api.unlinkSuperschool());
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card stack">
      <div className="row" style={{ gap: 14, alignItems: 'flex-start', flexWrap: 'nowrap' }}>
        <div className="feature-icon" style={{ width: 52, height: 52 }}>
          <School size={26} />
        </div>
        <div className="grow stack-sm">
          <div className="row">
            <h3>슈퍼스쿨</h3>
            {user.superschoolLinked ? (
              <span className="chip chip-ok">
                <CheckCircle2 size={13} /> 연결됨
              </span>
            ) : (
              <span className="chip">연결 안 됨</span>
            )}
          </div>
          {user.superschoolLinked && user.school && <span className="muted small">{user.school}</span>}
          <p className="muted small">연결하면 이런 정보를 가져와요. 비밀번호는 천천히에 저장되지 않아요.</p>
          <ul className="link-scope">
            <li>
              <CalendarDays size={16} /> 학사 일정 (시험, 행사, 휴업일) — 메인 화면 일정에 표시
            </li>
            <li>
              <UserRound size={16} /> 학교·학년·반 — 내 정보의 소속에 표시
            </li>
          </ul>
        </div>
      </div>
      <div className="row">
        {user.superschoolLinked ? (
          <button className="btn btn-ghost" onClick={unlink} disabled={busy}>
            <Unlink size={16} /> 연결 해제
          </button>
        ) : (
          <SuperschoolButton mode="link" returnTo="/settings?tab=links" />
        )}
      </div>
    </section>
  );
}
