// 서비스 로고: 옆에서 본 거북이 (등껍질 무늬 + 머리·다리). 색은 currentColor.
// index.html의 파비콘도 같은 모양입니다 (파란 바탕에 흰 거북이).
export function TurtleMark({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <g fill="currentColor">
        {/* 다리 */}
        <rect x="5.2" y="14" width="3.2" height="4.6" rx="1.6" />
        <rect x="13.6" y="14" width="3.2" height="4.6" rx="1.6" />
        {/* 꼬리 */}
        <path d="M3.6 14.2 1.4 15.6l2.6.6z" />
        {/* 머리 */}
        <circle cx="20" cy="11.6" r="2.6" />
        {/* 등껍질 */}
        <path d="M2.6 15.2C2.6 9.6 6.4 6 11 6s8.4 3.6 8.4 9.2z" />
      </g>
      {/* 등껍질 무늬 (바탕색으로 뚫어 보이게) */}
      <g fill="none" stroke="var(--turtle-cut, #3d6bf5)" strokeWidth="1.1" strokeLinejoin="round">
        <path d="M8.6 15.2V12.4L11 10.8l2.4 1.6v2.8" />
        <path d="M8.6 12.4 5.2 11.2M13.4 12.4l3.4-1.2M11 10.8V7.2" />
      </g>
      <circle cx="20.8" cy="11" r="0.7" fill="var(--turtle-cut, #3d6bf5)" />
    </svg>
  );
}
