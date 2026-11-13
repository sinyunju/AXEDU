// 교사 메인 화면 인사말. 새로고침할 때마다 하나를 무작위로 보여줍니다.
// 문구를 추가하려면 아래 목록에 한 줄만 더하면 됩니다.
export const TEACHER_GREETINGS = [
  '오늘도 힘내요!',
  '오늘도 파이팅!',
  '오늘 수업도 응원해요!',
  '오늘도 반가워요',
  '좋은 하루 보내세요!',
];

export function randomGreeting(list: string[] = TEACHER_GREETINGS) {
  return list[Math.floor(Math.random() * list.length)];
}
