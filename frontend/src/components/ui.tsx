// 여러 화면에서 쓰는 작은 UI 조각
import { ChevronLeft, Loader2 } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { LessonStatus } from '../api/types';
import { dateParts, lessonStatusChip, lessonStatusLabel } from '../lib/time';

export function Loading({ label = '불러오는 중…' }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <Loader2 size={20} className="spin" /> {label}
    </div>
  );
}

export function ErrorView({ message }: { message: string | null }) {
  return <div className="card center error-text">{message ?? '문제가 생겼어요'}</div>;
}

export function BackLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="back-link">
      <ChevronLeft size={18} /> {children}
    </Link>
  );
}

/** 회차 블록: "3회차 / 14 / 11월 토" (날짜가 없으면 회차 번호만 크게) */
export function DateBlock({ sessionNo, date }: { sessionNo: number; date?: string }) {
  const p = date ? dateParts(date) : null;
  return (
    <div className="date-block" aria-hidden>
      <span className="m">{sessionNo}회차</span>
      <span className="d">{p ? p.day : sessionNo}</span>
      <span className="m">{p ? `${p.month} ${p.weekday}` : '날짜 미정'}</span>
    </div>
  );
}

export function StatusChip({ status }: { status: LessonStatus }) {
  return <span className={`chip ${lessonStatusChip[status]}`}>{lessonStatusLabel[status]}</span>;
}

export function Empty({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon}</div>
      {children}
    </div>
  );
}
