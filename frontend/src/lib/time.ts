import type { LessonStatus } from '../api/types';

/** 'YYYY-MM-DD' → 그날 0시 (로컬) */
export function parseDate(date: string) {
  const [y, m, d] = date.split('-').map(Number);
  return new Date(y, m - 1, d);
}

/** 수업 날짜 표시: "11월 14일 (토)" / 날짜가 없으면 "날짜 미정" */
export function formatClassDate(date?: string) {
  if (!date) return '날짜 미정';
  return parseDate(date).toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'short' });
}

/** "오늘", "내일", "3일 후", "지남" (날짜 단위) */
export function daysLabel(date?: string) {
  if (!date) return '';
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diff = Math.round((parseDate(date).getTime() - today.getTime()) / 86_400_000);
  if (diff < 0) return '지남';
  if (diff === 0) return '오늘';
  if (diff === 1) return '내일';
  return `${diff}일 후`;
}

/** date 입력용 오늘 날짜 */
export function todayInput() {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** 날짜 블록용: { month: '11월', day: '14', weekday: '토' } */
export function dateParts(date: string) {
  const d = parseDate(date);
  return {
    month: `${d.getMonth() + 1}월`,
    day: String(d.getDate()),
    weekday: d.toLocaleDateString('ko-KR', { weekday: 'short' }),
  };
}

export const lessonStatusChip: Record<LessonStatus, string> = {
  uploaded: 'chip-warn',
  processing: 'chip-blue',
  review: 'chip-blue',
  approved: 'chip-ok',
  live: 'chip-bad',
  ended: '',
};

export const lessonStatusLabel: Record<LessonStatus, string> = {
  uploaded: '변환 전',
  processing: 'AI 변환 중',
  review: '검토 필요',
  approved: '준비 완료',
  live: '수업 중',
  ended: '수업 끝',
};
