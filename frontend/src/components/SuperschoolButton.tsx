// "슈퍼스쿨 계정으로 계속하기" 버튼. 실서버는 백엔드를 거쳐 슈퍼스쿨 인증 화면으로, 목 모드는 앱 안 흉내 화면으로 이동
import { School } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import type { Role } from '../api/types';
import { beginSuperschool, type SuperschoolMode } from '../lib/superschool';

interface Props {
  mode?: SuperschoolMode;
  role?: Role;
  returnTo?: string;
  label?: string;
  className?: string;
}

export function SuperschoolButton({ mode = 'login', role, returnTo, label, className = '' }: Props) {
  const navigate = useNavigate();

  function go() {
    const url = beginSuperschool(mode, { role, returnTo });
    if (url.startsWith('/')) navigate(url);
    else window.location.assign(url);
  }

  return (
    <button type="button" className={`btn btn-superschool ${className}`} onClick={go}>
      <span className="ss-mark">
        <School size={16} />
      </span>
      {label ?? (mode === 'login' ? '슈퍼스쿨 계정으로 계속하기' : '슈퍼스쿨 연결하기')}
    </button>
  );
}
