import { ChevronLeft, ChevronRight } from 'lucide-react';

interface Props {
  current: number;
  total: number;
  onChange: (page: number) => void;
}

export function PageNav({ current, total, onChange }: Props) {
  return (
    <div className="pager">
      <button
        className="btn btn-icon"
        aria-label="이전 페이지"
        onClick={() => onChange(current - 1)}
        disabled={current <= 1}
      >
        <ChevronLeft size={20} />
      </button>
      <span className="pager-label">
        <strong>{current}</strong> / {total}쪽
      </span>
      <button
        className="btn btn-icon btn-primary"
        aria-label="다음 페이지"
        onClick={() => onChange(current + 1)}
        disabled={current >= total}
      >
        <ChevronRight size={20} />
      </button>
    </div>
  );
}
