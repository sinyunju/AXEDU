// 슬라이드 선택 버튼: 선택 표시(thumb)가 옆으로 스르륵 움직임
import type { LucideIcon } from 'lucide-react';

interface Option<T extends string> {
  value: T;
  label: string;
  icon?: LucideIcon;
}

interface Props<T extends string> {
  options: Option<T>[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
  size?: 'sm' | 'md';
  /** tab: 화면 전환 탭, radio: 값 고르기 */
  kind?: 'tab' | 'radio';
  className?: string;
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
  size = 'md',
  kind = 'tab',
  className = '',
}: Props<T>) {
  const index = Math.max(0, options.findIndex((o) => o.value === value));
  const itemRole = kind === 'tab' ? 'tab' : 'radio';

  return (
    <div
      className={`seg seg-${size} ${className}`}
      role={kind === 'tab' ? 'tablist' : 'radiogroup'}
      aria-label={ariaLabel}
      style={{ '--seg-count': options.length, '--seg-index': index } as React.CSSProperties}
    >
      <span className="seg-thumb" aria-hidden />
      {options.map(({ value: v, label, icon: Icon }) => {
        const active = v === value;
        return (
          <button
            key={v}
            type="button"
            role={itemRole}
            aria-selected={kind === 'tab' ? active : undefined}
            aria-checked={kind === 'radio' ? active : undefined}
            className={active ? 'active' : ''}
            onClick={() => onChange(v)}
          >
            {Icon && <Icon size={size === 'sm' ? 15 : 17} />} {label}
          </button>
        );
      })}
    </div>
  );
}
