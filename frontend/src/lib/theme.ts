// 화면 테마. 기기(브라우저)마다 저장합니다.
// 'system'이면 <html>에 data-theme을 두지 않아 기기 설정(라이트=파랑, 다크=다크)을 따릅니다.
import { useCallback, useEffect, useState } from 'react';

export type ThemeChoice = 'system' | 'blue' | 'pink' | 'yellow' | 'dark';

export const THEMES: { value: ThemeChoice; label: string; swatch: string[] }[] = [
  { value: 'system', label: '시스템 설정', swatch: ['#3d6bf5', '#0c1224'] },
  { value: 'blue', label: '파랑', swatch: ['#3d6bf5', '#eef3ff'] },
  { value: 'pink', label: '핑크', swatch: ['#e94d8b', '#fdeef4'] },
  { value: 'yellow', label: '노랑', swatch: ['#f4b400', '#fff6d9'] },
  { value: 'dark', label: '다크', swatch: ['#5b84ff', '#0c1224'] },
];

const KEY = 'pref.theme';
const EVENT = 'themechange';

export function getTheme(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY) as ThemeChoice | null;
    return v && THEMES.some((t) => t.value === v) ? v : 'system';
  } catch {
    return 'system';
  }
}

export function applyTheme(theme: ThemeChoice) {
  const root = document.documentElement;
  if (theme === 'system') delete root.dataset.theme;
  else root.dataset.theme = theme;
  // 모바일 브라우저 주소창 색
  const primary = getComputedStyle(root).getPropertyValue('--primary').trim();
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', primary || '#3d6bf5');
}

export function setTheme(theme: ThemeChoice) {
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* 저장 못 해도 이번 화면에는 적용 */
  }
  applyTheme(theme);
  window.dispatchEvent(new Event(EVENT));
}

export function useTheme() {
  const [theme, setState] = useState<ThemeChoice>(getTheme);

  useEffect(() => {
    const sync = () => setState(getTheme());
    window.addEventListener(EVENT, sync);
    window.addEventListener('storage', sync); // 다른 탭에서 바꿨을 때
    return () => {
      window.removeEventListener(EVENT, sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  const change = useCallback((t: ThemeChoice) => setTheme(t), []);
  return [theme, change] as const;
}
