import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import './index.css';
import { applyTheme, getTheme } from './lib/theme';

// 첫 화면을 그리기 전에 테마를 적용해 깜빡임 방지
applyTheme(getTheme());
// 다른 탭에서 테마를 바꾸면 이 탭에도 반영
window.addEventListener('storage', (e) => e.key === 'pref.theme' && applyTheme(getTheme()));

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
