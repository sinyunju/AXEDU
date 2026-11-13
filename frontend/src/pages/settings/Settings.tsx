// 설정 (교사·학생 공용): 내 정보 · 화면 테마 · 계정 연동
import { Check, Link2, Monitor, Palette, UserRound } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { homeFor, useAuth } from '../../auth/AuthContext';
import { Segmented } from '../../components/Segmented';
import { BackLink } from '../../components/ui';
import { features } from '../../config';
import { THEMES, useTheme, type ThemeChoice } from '../../lib/theme';
import { LinksTab } from './LinksTab';
import { ProfileTab } from './ProfileTab';

const ALL_TABS = [
  { value: 'profile', label: '내 정보', icon: UserRound },
  { value: 'appearance', label: '화면 테마', icon: Palette },
  { value: 'links', label: '계정 연동', icon: Link2 },
] as const;
type Tab = (typeof ALL_TABS)[number]['value'];
// 계정 연동(슈퍼스쿨)은 백엔드에 아직 없어서 목 모드에서만
const TABS = ALL_TABS.filter((t) => t.value !== 'links' || features.superschool);

export function Settings() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab: Tab = TABS.some((t) => t.value === params.get('tab')) ? (params.get('tab') as Tab) : 'profile';

  // 탭이 오른쪽으로 가면 내용도 오른쪽에서, 왼쪽으로 가면 왼쪽에서 밀려 들어오게
  const index = TABS.findIndex((t) => t.value === tab);
  const prevIndex = useRef(index);
  const direction = index >= prevIndex.current ? 'next' : 'prev';
  useEffect(() => {
    prevIndex.current = index;
  }, [index]);

  if (!user) return null;

  return (
    <div className="stack narrow-page" style={{ maxWidth: 760 }}>
      <BackLink to={homeFor(user.role)}>처음으로</BackLink>
      <div className="page-head">
        <div>
          <span className="eyebrow">설정</span>
          <h2>{TABS.find((t) => t.value === tab)!.label}</h2>
        </div>
      </div>

      <Segmented
        ariaLabel="설정 메뉴"
        options={TABS}
        value={tab}
        onChange={(v) => setParams({ tab: v }, { replace: true })}
      />

      <div key={tab} className={`tab-panel slide-${direction}`} role="tabpanel">
        {tab === 'profile' && <ProfileTab />}
        {tab === 'appearance' && <AppearanceTab />}
        {tab === 'links' && features.superschool && <LinksTab />}
      </div>
    </div>
  );
}

function AppearanceTab() {
  const [theme, setTheme] = useTheme();

  return (
    <section className="card stack">
      <div>
        <h3>색 테마</h3>
        <p className="muted small">이 기기에서만 적용돼요. ‘시스템 설정’은 기기가 다크 모드면 다크, 아니면 파랑으로 보여요.</p>
      </div>
      <div className="theme-grid" role="radiogroup" aria-label="색 테마">
        {THEMES.map((t) => (
          <ThemeOption key={t.value} value={t.value} label={t.label} swatch={t.swatch} selected={theme === t.value} onSelect={setTheme} />
        ))}
      </div>
    </section>
  );
}

function ThemeOption({
  value,
  label,
  swatch,
  selected,
  onSelect,
}: {
  value: ThemeChoice;
  label: string;
  swatch: string[];
  selected: boolean;
  onSelect: (t: ThemeChoice) => void;
}) {
  const [main, bg] = swatch;
  const isSystem = value === 'system';
  const isDark = value === 'dark';
  return (
    <button role="radio" aria-checked={selected} className={`theme-option ${selected ? 'selected' : ''}`} onClick={() => onSelect(value)}>
      <span
        className="theme-preview"
        style={{
          background: isSystem ? `linear-gradient(135deg, #f3f6fd 50%, ${bg} 50%)` : bg,
        }}
      >
        <span className="tp-bar" style={{ background: main }} />
        <span className="tp-card" style={{ background: isDark ? '#151d35' : '#fff' }}>
          <i style={{ background: main }} />
          <i style={{ background: isDark ? '#33406b' : '#e3e8f4' }} />
        </span>
        {isSystem && <Monitor size={16} className="tp-icon" />}
      </span>
      <span className="theme-label">
        {label}
        {selected && <Check size={16} />}
      </span>
    </button>
  );
}
