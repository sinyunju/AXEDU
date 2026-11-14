// 화면이 쓰는 데이터 형식 (프론트 도메인 모델).
// 백엔드 형식(backend.d.ts)과의 변환은 api/index.ts의 어댑터에서만 합니다.

/** 계정. 교사·학생 공용이며 role로 구분합니다. */
export type Role = 'teacher' | 'student';

export interface User {
  id: string;
  role: Role;
  username: string; // 로그인 아이디 (백엔드 login_id)
  name: string;
  email?: string;
  avatarUrl?: string; // 프로필 사진 (목 모드 전용)
  school?: string; // 슈퍼스쿨 연동 시 채워짐 (목 모드 전용)
  superschoolLinked: boolean;
}

export interface AuthResponse {
  token: string;
  user: User;
}

export interface SignupInput {
  role: Role;
  username: string;
  password: string;
  name: string;
}

export interface ProfileInput {
  name?: string;
  email?: string;
  avatarUrl?: string | null; // null이면 사진 삭제
}

/** 메인 화면 캘린더 일정 (목 모드 전용) */
export interface CalendarEvent {
  id: string;
  title: string;
  start: string; // ISO
  end?: string;
  allDay: boolean;
  source: 'superschool' | 'lesson';
  category?: string;
  lessonId?: string;
  lessonStatus?: LessonStatus;
  courseName?: string;
}

export interface CalendarResponse {
  superschoolLinked: boolean;
  events: CalendarEvent[];
}

/** 과목: 교사가 개설하고, 학생은 초대 코드로 들어옴 */
export interface Course {
  id: string;
  name: string;
  subject: string; // 과목 설명 (백엔드 description)
  joinCode?: string; // 초대 코드 6자 (영문·숫자). 학생에게는 없음
  teacherName: string;
  lessonCount?: number; // 과목 목록 응답에는 없을 수 있음
}

/**
 * 회차 상태 (백엔드 → 화면)
 * - uploaded   → uploaded   PDF만 올라감, AI 변환 전
 * - generating → processing AI 변환 중 (progress 0~100)
 * - ready      → review     교사 검토 필요
 * - approved   → approved   학생에게 공개
 * - live       → live       수업 중
 * - ended      → ended      수업 끝 (다시 시작 가능)
 */
export type LessonStatus = 'uploaded' | 'processing' | 'review' | 'approved' | 'live' | 'ended';

/** 학생이 들어갈 수 있는 상태 */
export const OPEN_TO_STUDENTS: LessonStatus[] = ['approved', 'live', 'ended'];

/** 어려운 말 풀이 */
export interface Term {
  word: string;
  meaning: string;
}

export interface PageImage {
  url?: string; // 생성 전이면 비어 있음
  reason: string; // AI가 이미지가 필요하다고 본 이유
  prompt?: string; // AI가 제안한 이미지 설명
  approved: boolean;
}

export interface LessonPage {
  index: number; // 1부터 (백엔드 page_no)
  originalImageUrl?: string; // PDF 페이지 이미지
  originalText: string; // 원문 (교사에게만)
  easyText: string; // 쉬운 문장. 한 줄에 한 문장 (백엔드 easy_sentences)
  terms: Term[];
  image?: PageImage;
}

/** 과목 안의 한 회차 */
export interface Lesson {
  id: string;
  courseId: string;
  sessionNo: number;
  title: string;
  classDate?: string; // YYYY-MM-DD
  status: LessonStatus;
  progress: number; // AI 변환 진행률 0~100
  currentPage: number; // 선생님이 보고 있는 페이지
  pages: LessonPage[];
}

export interface LessonSummary {
  id: string;
  courseId: string;
  sessionNo: number;
  title: string;
  classDate?: string;
  status: LessonStatus;
  progress: number;
  pageCount?: number;
}

export interface NewLessonInput {
  file: File;
  sessionNo: number;
  title: string;
  classDate?: string; // YYYY-MM-DD
}

/**
 * 실시간 쉬운 자막 한 줄
 * - content: 수업 내용
 * - flow: 수업 흐름 안내 ("지금부터 정리해요") → 구분선·작은 글씨
 * - notice: 과제·준비물 안내 → 강조 상자 + "과제" 배지
 */
export interface CaptionItem {
  text: string;
  kind: 'content' | 'flow' | 'notice';
}

/** 한 페이지의 실시간 자막 묶음 (page_update로 통째 교체) */
export interface PageCaptions {
  items: CaptionItem[];
  hardWords: Term[];
}

/** 학생 화면용 페이지 정보 (자막 + 선생님 위치) */
export interface PageLiveView extends PageCaptions {
  pageIndex: number;
  teacherPage: number;
  lessonStatus: LessonStatus;
}

/** 퀴즈 문항. 학생에게는 정답이 오지 않음 → 제출 후 채점 결과로 확인 */
export interface QuizItem {
  id: string;
  type: 'ox' | 'choice';
  question: string;
  choices: string[]; // OX면 ['O', 'X']
  pageIndex?: number;
}

export interface QuizAnswer {
  questionId: string;
  answer: string; // 보기 글 그대로 (OX는 "O"/"X")
}

export interface QuizResultItem {
  questionId: string;
  answer: string | null;
  correct: boolean;
  correctAnswer: string;
  explanation: string;
  pageIndex?: number;
}

export interface QuizResult {
  score: number;
  total: number;
  submittedAt: string;
  results: QuizResultItem[];
}

export interface ChatMessage {
  from: 'me' | 'bot';
  text: string;
  relatedPage?: number;
}

export interface ChatReply {
  answer: string;
  relatedPage?: number;
}

/** 수업 자료 위 필기 한 획. 좌표·굵기는 페이지 너비·높이 기준 0~1 비율 */
export interface Stroke {
  tool: 'pen' | 'highlighter';
  color: string; // #rrggbb
  width: number; // 페이지 너비 대비
  points: [number, number][];
}

/** 레이저 포인터 위치 (0~1). null이면 숨김 */
export type PointerPos = { x: number; y: number } | null;

/** WebSocket: 서버 → 화면 */
export type ServerMessage =
  | { type: 'teacher_page'; pageIndex: number }
  | { type: 'page_update'; pageIndex: number; captions: PageCaptions }
  | { type: 'lesson_started'; pageIndex: number }
  | { type: 'lesson_ended' }
  | { type: 'ack'; for: 'transcript' | 'page_change'; pageIndex: number; ignored?: boolean }
  | { type: 'error'; detail: string }
  /** 선생님 레이저 포인터 (학생에게만 옴) */
  | { type: 'pointer'; pageIndex: number; pos: PointerPos }
  /** 서버가 연결을 거부함 (4401/4403/4404). 재연결하지 않음 */
  | { type: 'rejected'; code: number; reason: string };

/** WebSocket: 교사 → 서버 */
export type TeacherMessage =
  | { type: 'page_change'; pageIndex: number }
  | { type: 'transcript'; pageIndex: number; text: string }
  | { type: 'pointer'; pageIndex: number; pos: PointerPos };
