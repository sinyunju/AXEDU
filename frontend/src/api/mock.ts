// 백엔드 없이 화면을 개발하기 위한 목 구현. 실서버(real.ts)와 같은 함수·같은 동작을 흉내 냅니다.
// 데이터는 localStorage에 두어 교사 탭과 학생 탭이 같은 데이터를 봅니다.
// 비밀번호를 평문으로 두므로 실제 서비스에서는 절대 쓰지 않습니다.
import { randomId } from '../lib/id';
import { ApiError } from './http';
import type { Api } from './real';
import { getToken } from './token';
import type {
  AuthResponse,
  CalendarEvent,
  CalendarResponse,
  CaptionItem,
  ChatMessage,
  ChatReply,
  Course,
  Lesson,
  LessonPage,
  LessonSummary,
  NewLessonInput,
  PageCaptions,
  PageLiveView,
  ProfileInput,
  QuizAnswer,
  QuizItem,
  QuizResult,
  SignupInput,
  Stroke,
  User,
} from './types';
import { OPEN_TO_STUDENTS } from './types';

// ---------- 저장소 ----------
// 데이터 구조가 바뀌면 키 버전을 올려 예전 목 데이터를 무시합니다.

export const MOCK_KEYS = {
  users: 'mock.users.v3',
  courses: 'mock.courses.v3',
  enrollments: 'mock.enrollments.v3', // { [studentId]: courseId[] }
  lessons: 'mock.lessons.v5',
  captions: 'mock.captions.v3', // { [lessonId]: { [page]: PageCaptions } }
  quizzes: 'mock.quizzes.v1', // { [lessonId]: MockQuestion[] }
  attempts: 'mock.attempts.v1', // { [`${lessonId}:${userId}`]: QuizResult[] }
  chats: 'mock.chats.v1', // { [`${lessonId}:${userId}`]: ChatMessage[] }
  teacherPage: 'mock.teacherPage', // + `.${lessonId}`
  annotations: 'mock.annotations.v1', // { [`${lessonId}:${userId}`]: { [page]: Stroke[] } }
};
const KEYS = MOCK_KEYS;

function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function save(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* 저장 실패해도 화면은 동작 */
  }
}

const delay = (ms = 300) => new Promise((r) => setTimeout(r, ms));
const newId = () => randomId(4);
const INVITE_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
const inviteCode = () =>
  Array.from(crypto.getRandomValues(new Uint8Array(6)), (b) => INVITE_ALPHABET[b % INVITE_ALPHABET.length]).join('');
const fail = (status: number, message: string) => new ApiError(status, message);

/** 문장 끝마다 줄바꿈 (화면의 쉬운 문장은 한 줄에 한 문장) */
const sentences = (s: string) => s.replace(/([.!?])\s+/g, '$1\n').trim();

/** 오늘 기준 며칠 뒤 날짜 (YYYY-MM-DD) */
function dateFromToday(days: number) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// ---------- 시드 데이터 (백엔드 scripts/seed.py와 같은 계정·과목) ----------

type MockUser = User & { password: string };
type MockCourse = Omit<Course, 'teacherName' | 'lessonCount'> & { teacherId: string; joinCode: string };
type MockLesson = Lesson & { generateStartedAt?: number };
type MockQuestion = QuizItem & { answer: string; explanation: string };

const DEMO_PASSWORD = 'pass1234';
const seedUsers: MockUser[] = [
  { id: 't1', role: 'teacher', username: 'teacher1', name: '김선생', superschoolLinked: false, password: DEMO_PASSWORD },
  { id: 's1', role: 'student', username: 'student1', name: '이학생', superschoolLinked: false, password: DEMO_PASSWORD },
  { id: 's2', role: 'student', username: 'student2', name: '박학생', superschoolLinked: false, password: DEMO_PASSWORD },
  { id: 's3', role: 'student', username: 'student3', name: '최학생', superschoolLinked: false, password: DEMO_PASSWORD },
];

const seedCourses: MockCourse[] = [
  { id: 'c1', name: '과학', subject: '데모용 과목', joinCode: 'DEMO01', teacherId: 't1' },
];

/** 예시 이미지 (인터넷 없이도 보이도록 SVG를 직접 만듦) */
const img = (text: string) => {
  const safe = text.replace(/[<>&"]/g, '');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#eef3ff"/><stop offset="1" stop-color="#dde7ff"/></linearGradient></defs>
<rect width="640" height="360" fill="url(#g)"/>
<circle cx="560" cy="60" r="90" fill="#3d6bf5" opacity=".08"/><circle cx="80" cy="320" r="70" fill="#3d6bf5" opacity=".08"/>
<text x="320" y="170" text-anchor="middle" font-family="Pretendard, 'Malgun Gothic', sans-serif" font-size="26" font-weight="700" fill="#2546b9">${safe}</text>
<text x="320" y="210" text-anchor="middle" font-family="Pretendard, 'Malgun Gothic', sans-serif" font-size="15" fill="#6c7695">(AI 생성 이미지 자리)</text>
</svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
};

/** 중2 과학 「식물과 에너지」 단원을 바탕으로 만든 예시 자료 (5쪽) */
const samplePages: LessonPage[] = [
  {
    index: 1,
    originalText:
      '광합성은 식물이 빛에너지를 이용하여 이산화 탄소와 물로 포도당을 합성하는 과정이다. 이때 빛에너지는 포도당 속에 화학 에너지의 형태로 저장된다. 광합성 결과 만들어진 포도당은 식물이 생명 활동을 하는 데 필요한 에너지원으로 쓰이며, 동물을 비롯한 다른 생물도 식물을 먹이로 삼아 이 에너지를 얻는다. 따라서 광합성은 지구 생태계를 유지하는 에너지의 출발점이라고 할 수 있다. 또한 광합성 과정에서 방출되는 산소는 대부분의 생물이 호흡하는 데 이용된다.',
    easyText: sentences(
      '광합성은 식물이 햇빛으로 양분을 만드는 일이에요. 식물은 공기 속 이산화 탄소와 뿌리로 빨아들인 물을 재료로 써요. 그 결과 포도당이라는 양분이 생겨요. 햇빛의 에너지는 포도당 안에 저장돼요. 식물은 이 포도당으로 살아가고 자라요. 동물은 식물을 먹어서 이 에너지를 얻어요. 그래서 광합성은 지구의 모든 생물에게 에너지를 나눠 주는 출발점이에요. 광합성을 할 때 나오는 산소는 우리가 숨 쉬는 데 쓰여요.',
    ),
    terms: [
      { word: '광합성', meaning: '식물이 햇빛을 받아 스스로 양분을 만드는 일' },
      { word: '이산화 탄소', meaning: '숨을 내쉴 때 나오는, 눈에 보이지 않는 기체' },
      { word: '포도당', meaning: '식물이 만드는 단맛이 나는 양분' },
      { word: '에너지', meaning: '움직이고 자라는 데 필요한 힘' },
      { word: '산소', meaning: '우리가 숨 쉴 때 꼭 필요한 기체' },
    ],
    image: { url: img('이산화 탄소 + 물 → 포도당 + 산소'), reason: '재료 → 결과로 이어지는 과정', approved: true },
  },
  {
    index: 2,
    originalText:
      '광합성은 주로 잎의 엽록체에서 일어난다. 엽록체는 식물 세포에 있는 초록색의 작은 알갱이로, 빛을 흡수하는 엽록소라는 색소를 가지고 있다. 잎의 표피에는 공변세포 두 개가 둘러싼 작은 구멍인 기공이 있는데, 광합성에 필요한 이산화 탄소는 이 기공을 통해 잎 안으로 들어오고, 광합성 결과 생긴 산소는 기공을 통해 밖으로 나간다. 기공은 주로 잎의 뒷면에 많이 분포하며, 낮에 열리고 밤에 닫히는 경우가 많다.',
    easyText: sentences(
      '광합성은 주로 잎 속 엽록체에서 일어나요. 엽록체는 잎을 초록색으로 보이게 하는 작은 알갱이예요. 엽록체 안에는 햇빛을 받아들이는 엽록소가 있어요. 잎 겉에는 기공이라는 아주 작은 구멍이 있어요. 이산화 탄소는 기공으로 들어오고, 산소는 기공으로 나가요. 기공은 잎의 뒷면에 많아요. 보통 낮에 열리고 밤에 닫혀요.',
    ),
    terms: [
      { word: '엽록체', meaning: '잎 속에서 광합성을 하는 작은 초록색 알갱이' },
      { word: '엽록소', meaning: '햇빛을 받아들이는 초록색 물질' },
      { word: '기공', meaning: '잎 겉에 있는 아주 작은 숨구멍' },
      { word: '세포', meaning: '생물의 몸을 이루는 아주 작은 기본 단위' },
    ],
    image: { url: img('잎의 단면: 엽록체와 기공'), reason: '눈으로 보기 어려운 구조(공간 관계)', approved: true },
  },
  {
    index: 3,
    originalText:
      '광합성의 재료인 물은 뿌리털에서 흡수되어 줄기의 물관을 거쳐 잎까지 이동한다. 이산화 탄소는 앞에서 살펴본 것처럼 기공을 통해 공기 중에서 흡수된다. 엽록체에서 만들어진 포도당은 곧 물에 잘 녹지 않는 녹말로 바뀌어 잎에 잠시 저장된다. 녹말은 아이오딘-아이오딘화 칼륨 용액과 반응하여 청람색을 띠므로, 이 용액을 이용하면 잎에서 광합성이 일어났는지 확인할 수 있다. 한편 산소는 일부가 식물의 호흡에 쓰이고 나머지는 공기 중으로 방출된다.',
    easyText: sentences(
      '물은 뿌리로 들어와서 줄기 속 물관을 타고 잎까지 올라가요. 이산화 탄소는 기공으로 들어와요. 잎에서 만든 포도당은 곧 녹말로 바뀌어 잎에 잠깐 저장돼요. 녹말에 아이오딘 용액을 떨어뜨리면 청람색(진한 파란색)으로 바뀌어요. 그래서 이 용액으로 잎이 광합성을 했는지 알아볼 수 있어요. 산소는 식물이 조금 쓰고, 나머지는 공기 중으로 나가요.',
    ),
    terms: [
      { word: '물관', meaning: '물이 뿌리에서 잎까지 올라가는 길' },
      { word: '녹말', meaning: '포도당이 여러 개 이어진, 물에 잘 안 녹는 양분' },
      { word: '아이오딘 용액', meaning: '녹말이 있으면 파랗게 변하는 확인용 물약' },
      { word: '청람색', meaning: '푸른빛이 도는 진한 남색' },
    ],
  },
  {
    index: 4,
    originalText:
      '광합성량은 빛의 세기, 이산화 탄소의 농도, 온도 등의 환경 요인에 영향을 받는다. 빛의 세기가 강해질수록 광합성량은 증가하지만, 일정 세기 이상이 되면 더 이상 증가하지 않는다. 이산화 탄소의 농도도 마찬가지로 높아질수록 광합성량이 증가하다가 일정 농도 이상에서는 거의 변하지 않는다. 온도의 경우 일정 온도까지는 온도가 높아질수록 광합성량이 증가하지만, 그 이상에서는 광합성에 관여하는 효소가 제대로 작용하지 못해 광합성량이 급격히 감소한다.',
    easyText: sentences(
      '광합성을 얼마나 많이 하는지는 햇빛, 이산화 탄소, 온도에 따라 달라져요. 햇빛이 셀수록 광합성을 더 많이 해요. 하지만 어느 정도를 넘으면 더 늘지 않아요. 이산화 탄소도 많을수록 광합성이 늘다가, 어느 정도부터는 그대로예요. 온도는 알맞게 따뜻할 때 광합성이 가장 활발해요. 너무 뜨거워지면 광합성을 돕는 효소가 일을 못 해서 광합성이 확 줄어요.',
    ),
    terms: [
      { word: '광합성량', meaning: '광합성을 얼마나 많이 했는지 나타내는 양' },
      { word: '농도', meaning: '어떤 것이 얼마나 많이 섞여 있는지' },
      { word: '환경 요인', meaning: '생물에게 영향을 주는 주변 조건' },
      { word: '효소', meaning: '몸속에서 일이 잘 일어나게 돕는 물질' },
    ],
    image: { reason: '조건에 따라 변하는 양(그래프)', prompt: '빛의 세기에 따른 광합성량 그래프', approved: false },
  },
  {
    index: 5,
    originalText:
      '낮 동안 잎에 저장된 녹말은 주로 밤에 물에 잘 녹는 설탕으로 바뀌어 체관을 통해 식물의 각 부분으로 이동한다. 이동한 양분은 세포 호흡을 통해 생명 활동에 필요한 에너지를 얻는 데 쓰이거나, 식물의 몸을 구성하는 성분이 된다. 쓰이고 남은 양분은 뿌리, 줄기, 열매, 씨 등에 녹말, 단백질, 지방 등 다양한 형태로 저장된다. 예를 들어 감자는 줄기에, 고구마는 뿌리에 녹말을 저장하며, 콩은 씨에 단백질을 많이 저장한다.',
    easyText: sentences(
      '낮에 잎에 모아 둔 녹말은 밤이 되면 설탕으로 바뀌어요. 설탕은 물에 잘 녹아서 체관을 타고 식물 곳곳으로 옮겨져요. 옮겨진 양분은 식물이 살아가는 힘을 내거나 몸을 만드는 데 쓰여요. 쓰고 남은 양분은 뿌리, 줄기, 열매, 씨에 저장돼요. 감자는 줄기에, 고구마는 뿌리에 녹말을 모아 둬요. 콩은 씨에 단백질을 많이 모아 둬요.',
    ),
    terms: [
      { word: '체관', meaning: '잎에서 만든 양분이 식물 곳곳으로 옮겨 가는 길' },
      { word: '세포 호흡', meaning: '양분을 써서 살아가는 힘을 얻는 일' },
      { word: '저장', meaning: '나중에 쓰려고 모아 두는 것' },
      { word: '단백질', meaning: '몸을 만드는 데 쓰이는 영양소' },
    ],
  },
];

/** 업로드 직후(변환 전) 페이지: 원문만 있음 */
const rawPages = (): LessonPage[] =>
  samplePages.map((p) => ({ index: p.index, originalText: p.originalText, easyText: '', terms: [] }));

const lessonBase = { progress: 100, currentPage: 1 };
const seedLessons: MockLesson[] = [
  { ...lessonBase, id: 'l1', courseId: 'c1', sessionNo: 1, title: '광합성', classDate: dateFromToday(0), status: 'approved', pages: samplePages },
  { ...lessonBase, id: 'l2', courseId: 'c1', sessionNo: 2, title: '식물의 호흡', classDate: dateFromToday(1), status: 'review', pages: structuredClone(samplePages) },
  { ...lessonBase, id: 'l3', courseId: 'c1', sessionNo: 3, title: '광합성과 호흡 비교', classDate: dateFromToday(3), status: 'uploaded', progress: 0, pages: rawPages() },
];

const seedCaptions: Record<string, Record<number, PageCaptions>> = {
  l1: {
    1: {
      items: [
        { text: '지금부터 광합성을 배워요.', kind: 'flow' },
        { text: '광합성은 식물이 밥을 스스로 만드는 방법이에요.', kind: 'content' },
        { text: '재료는 이산화 탄소와 물이고, 에너지는 햇빛에서 와요.', kind: 'content' },
      ],
      hardWords: [],
    },
    2: {
      items: [
        { text: '엽록체가 있어서 잎이 초록색으로 보여요.', kind: 'content' },
        { text: '기공은 잎 뒷면에 많아요. 숨구멍이라고 생각하면 돼요.', kind: 'content' },
        { text: '다음 시간까지 잎 하나를 가져와요.', kind: 'notice' },
      ],
      hardWords: [{ word: '숨구멍', meaning: '숨을 쉬는 작은 구멍' }],
    },
  },
};

const sampleQuiz: MockQuestion[] = [
  { id: 'q1', type: 'ox', question: '광합성을 하면 산소가 나온다.', choices: ['O', 'X'], answer: 'O', explanation: '맞아요. 광합성을 하면 산소가 밖으로 나와요.', pageIndex: 1 },
  { id: 'q2', type: 'choice', question: '광합성은 주로 어디에서 일어날까요?', choices: ['뿌리', '엽록체', '줄기'], answer: '엽록체', explanation: '광합성은 잎 속 엽록체에서 일어나요.', pageIndex: 2 },
  { id: 'q3', type: 'choice', question: '잎에 녹말이 있는지 알아볼 때 쓰는 것은 무엇일까요?', choices: ['아이오딘 용액', '소금물', '석회수'], answer: '아이오딘 용액', explanation: '녹말에 아이오딘 용액을 떨어뜨리면 청람색으로 바뀌어요.', pageIndex: 3 },
];

const users = () => load<MockUser[]>(KEYS.users, seedUsers);
const saveUsers = (list: MockUser[]) => save(KEYS.users, list);
const courses = () => load<MockCourse[]>(KEYS.courses, seedCourses);
const enrollments = () => load<Record<string, string[]>>(KEYS.enrollments, { s1: ['c1'], s2: ['c1'], s3: ['c1'] });
const lessons = () => load<MockLesson[]>(KEYS.lessons, seedLessons);
const saveLessons = (list: MockLesson[]) => save(KEYS.lessons, list);
const captions = () => load<Record<string, Record<number, PageCaptions>>>(KEYS.captions, seedCaptions);
const quizzes = () => load<Record<string, MockQuestion[]>>(KEYS.quizzes, { l1: sampleQuiz });

// ---------- 헬퍼 ----------

function publicUser({ password: _pw, ...u }: MockUser): User {
  return u;
}

function issue(u: MockUser): AuthResponse {
  return { token: `mock.${u.id}`, user: publicUser(u) };
}

function currentUser(): MockUser {
  const id = getToken()?.replace(/^mock\./, '');
  const u = users().find((x) => x.id === id);
  if (!u) throw fail(401, '로그인이 필요해요');
  return u;
}

function patchUser(id: string, patch: Partial<MockUser>): MockUser {
  let updated!: MockUser;
  saveUsers(users().map((u) => (u.id === id ? (updated = { ...u, ...patch }) : u)));
  return updated;
}

function toCourse(c: MockCourse, viewer: MockUser): Course {
  const { teacherId, joinCode, ...rest } = c;
  return {
    ...rest,
    joinCode: viewer.role === 'teacher' ? joinCode : undefined, // 학생에게는 초대 코드를 주지 않음 (백엔드와 같게)
    teacherName: users().find((u) => u.id === teacherId)?.name ?? '',
    lessonCount: lessons().filter((l) => l.courseId === c.id).length,
  };
}

/** 이 사용자가 과목에 접근할 수 있는지 (교사: 개설자, 학생: 참여자) */
function canAccessCourse(u: MockUser, courseId: string) {
  const c = courses().find((x) => x.id === courseId);
  if (!c) return false;
  return u.role === 'teacher' ? c.teacherId === u.id : (enrollments()[u.id] ?? []).includes(courseId);
}

/** AI 변환 흉내: 시작 후 약 4초에 걸쳐 진행률이 오르고, 끝나면 검토 단계로 */
function advance(l: MockLesson): MockLesson {
  if (l.status !== 'processing' || !l.generateStartedAt) return l;
  const progress = Math.min(100, Math.round(((Date.now() - l.generateStartedAt) / 4000) * 100));
  if (progress < 100) return { ...l, progress };
  const done: MockLesson = {
    ...l,
    status: 'review',
    progress: 100,
    generateStartedAt: undefined,
    pages: l.pages.map((p, i) => {
      const s = samplePages[i % samplePages.length];
      return { ...p, easyText: s.easyText, terms: s.terms, image: s.image && { ...s.image, approved: false } };
    }),
  };
  saveLessons(lessons().map((x) => (x.id === l.id ? done : x)));
  return done;
}

function findLesson(id: string, opts: { teacherOnly?: boolean } = {}): MockLesson {
  const u = currentUser();
  const l = lessons().find((x) => x.id === id);
  if (!l || !canAccessCourse(u, l.courseId)) throw fail(404, '수업 회차를 찾을 수 없습니다');
  if (opts.teacherOnly && u.role !== 'teacher') throw fail(403, '교사만 할 수 있습니다');
  if (u.role === 'student' && !OPEN_TO_STUDENTS.includes(l.status)) throw fail(404, '수업 회차를 찾을 수 없습니다');
  return advance(l);
}

function patchLesson(id: string, patch: Partial<MockLesson>): MockLesson {
  let updated!: MockLesson;
  saveLessons(lessons().map((l) => (l.id === id ? (updated = { ...l, ...patch }) : l)));
  return updated;
}

function toSummary({ pages, currentPage: _c, generateStartedAt: _g, ...rest }: MockLesson): LessonSummary {
  return { ...rest, pageCount: pages.length };
}

/** 학생에게는 승인 전 내용·원문을 보여주지 않음 (백엔드와 같게) */
function forViewer(l: MockLesson, viewer: MockUser): Lesson {
  const { generateStartedAt: _g, ...lesson } = l;
  if (viewer.role === 'teacher') return lesson;
  return { ...lesson, pages: lesson.pages.map((p) => ({ ...p, originalText: '' })) };
}

/** 같은 브라우저의 다른 탭(학생 화면)에 실시간 메시지 보내기 */
function broadcast(lessonId: string, msg: unknown) {
  try {
    const bc = new BroadcastChannel(`live:${lessonId}`);
    bc.postMessage(msg);
    bc.close();
  } catch {
    /* 무시 */
  }
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error);
    r.readAsDataURL(blob);
  });
}

/** 슈퍼스쿨에서 받아왔다고 가정하는 정보 */
const superschoolProfile = (role: User['role']) => ({
  school: role === 'teacher' ? '천천중학교 · 과학과' : '천천중학교 2학년 3반',
  superschoolLinked: true,
});

function dayFromToday(days: number) {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + days);
  return d.toISOString();
}

/** 슈퍼스쿨 학사 일정 예시 */
function superschoolEvents(): CalendarEvent[] {
  const e = (id: string, title: string, days: number, category: string, endDays?: number): CalendarEvent => ({
    id: `ss-${id}`,
    title,
    start: dayFromToday(days),
    end: endDays !== undefined ? dayFromToday(endDays) : undefined,
    allDay: true,
    source: 'superschool',
    category,
  });
  return [
    e('club', '동아리 활동', 0, '행사'),
    e('counsel', '학부모 상담 주간', 1, '행사', 4),
    e('holiday', '재량휴업일', 5, '휴업일'),
    e('fieldtrip', '진로 체험학습', 8, '행사'),
    e('exam', '2학기 기말고사', 12, '시험', 14),
    e('festival', '학교 축제', 19, '행사'),
  ];
}

/** 교사 말 → 쉬운 자막 흉내. 실서버에서는 AI가 내용/흐름/과제를 나눔 */
function toCaption(text: string): CaptionItem {
  if (/과제|숙제|준비물|가져와|가지고 와/.test(text)) return { text, kind: 'notice' };
  if (/^(지금부터|이제|자,|다음은|정리)/.test(text)) return { text, kind: 'flow' };
  return { text: `(쉬운 말) ${text}`, kind: 'content' };
}

function getTeacherPage(lessonId: string, fallback: number) {
  try {
    return Number(localStorage.getItem(`${KEYS.teacherPage}.${lessonId}`)) || fallback;
  } catch {
    return fallback;
  }
}

// ---------- API ----------

export const mockApi: Api & {
  addTranscript: (lessonId: string, pageIndex: number, text: string) => PageCaptions | null;
} = {
  // 인증
  async login(username: string, password: string): Promise<AuthResponse> {
    await delay();
    const u = users().find((x) => x.username === username && x.password === password);
    if (!u) throw fail(401, '아이디 또는 비밀번호가 올바르지 않습니다');
    return issue(u);
  },

  async signup(input: SignupInput): Promise<AuthResponse> {
    await delay();
    const list = users();
    if (list.some((x) => x.username === input.username)) throw fail(409, '이미 사용 중인 아이디입니다');
    const u: MockUser = { id: newId(), superschoolLinked: false, ...input };
    saveUsers([...list, u]);
    return issue(u);
  },

  async me(): Promise<User> {
    await delay(100);
    return publicUser(currentUser());
  },

  // 슈퍼스쿨 연동 (목 모드 전용)
  superschoolAuthorizeUrl(mode: 'login' | 'link', role?: User['role']) {
    const q = new URLSearchParams({ mode, ...(role ? { role } : {}) });
    return `/auth/superschool/mock?${q}`;
  },

  /** 목: code = 'mock:teacher' | 'mock:student' → 데모 계정으로 로그인 */
  async superschoolLogin(code: string): Promise<AuthResponse> {
    await delay(500);
    const role = code === 'mock:teacher' ? 'teacher' : 'student';
    return issue(patchUser(role === 'teacher' ? 't1' : 's1', superschoolProfile(role)));
  },

  async linkSuperschool(_code: string): Promise<User> {
    await delay(500);
    const u = currentUser();
    return publicUser(patchUser(u.id, superschoolProfile(u.role)));
  },

  async unlinkSuperschool(): Promise<User> {
    await delay();
    return publicUser(patchUser(currentUser().id, { superschoolLinked: false, school: undefined }));
  },

  // 프로필 (목 모드 전용)
  async updateMe(input: ProfileInput): Promise<User> {
    await delay();
    const patch: Partial<MockUser> = { ...input, avatarUrl: input.avatarUrl ?? undefined };
    if (input.avatarUrl === undefined) delete patch.avatarUrl;
    return publicUser(patchUser(currentUser().id, patch));
  },

  async uploadAvatar(file: Blob): Promise<{ avatarUrl: string }> {
    await delay(400);
    return { avatarUrl: await blobToDataUrl(file) };
  },

  async changePassword(current: string, next: string): Promise<void> {
    await delay();
    const u = currentUser();
    if (u.password !== current) throw fail(400, '지금 비밀번호가 맞지 않아요');
    patchUser(u.id, { password: next });
  },

  // 캘린더 (목 모드 전용)
  async getCalendar(from: string, to: string): Promise<CalendarResponse> {
    await delay();
    const u = currentUser();
    const lessonEvents: CalendarEvent[] = lessons()
      .filter((l) => l.classDate && canAccessCourse(u, l.courseId))
      .filter((l) => u.role === 'teacher' || OPEN_TO_STUDENTS.includes(l.status))
      .map((l) => ({
        id: `lesson-${l.id}`,
        title: `${l.sessionNo}회차 ${l.title}`,
        start: new Date(`${l.classDate}T00:00:00`).toISOString(),
        allDay: true,
        source: 'lesson',
        category: '수업',
        lessonId: l.id,
        lessonStatus: l.status,
        courseName: courses().find((c) => c.id === l.courseId)?.name,
      }));
    const all = [...(u.superschoolLinked ? superschoolEvents() : []), ...lessonEvents];
    const inRange = all.filter((e) => (e.end ?? e.start) >= from && e.start < to);
    return { superschoolLinked: u.superschoolLinked, events: inRange.sort((a, b) => a.start.localeCompare(b.start)) };
  },

  // 과목
  async listCourses(): Promise<Course[]> {
    await delay();
    const u = currentUser();
    return courses()
      .filter((c) => canAccessCourse(u, c.id))
      .map((c) => toCourse(c, u));
  },

  async createCourse(name: string, subject: string): Promise<Course> {
    await delay();
    const u = currentUser();
    if (u.role !== 'teacher') throw fail(403, '교사만 할 수 있습니다');
    const c: MockCourse = { id: newId(), name, subject, joinCode: inviteCode(), teacherId: u.id };
    save(KEYS.courses, [...courses(), c]);
    return toCourse(c, u);
  },

  async getCourse(id: string): Promise<Course> {
    await delay();
    const u = currentUser();
    const c = courses().find((x) => x.id === id);
    if (!c || !canAccessCourse(u, id)) throw fail(404, '과목을 찾을 수 없습니다');
    return toCourse(c, u);
  },

  async joinCourse(code: string): Promise<Course> {
    await delay();
    const u = currentUser();
    if (u.role !== 'student') throw fail(403, '학생만 할 수 있습니다');
    const c = courses().find((x) => x.joinCode === code.trim().toUpperCase());
    if (!c) throw fail(404, '초대 코드에 맞는 과목이 없습니다');
    const all = enrollments();
    if ((all[u.id] ?? []).includes(c.id)) throw fail(409, '이미 등록한 과목입니다');
    all[u.id] = [...(all[u.id] ?? []), c.id];
    save(KEYS.enrollments, all);
    return toCourse(c, u);
  },

  // 회차
  async listLessons(courseId: string): Promise<LessonSummary[]> {
    await delay();
    const u = currentUser();
    if (!canAccessCourse(u, courseId)) throw fail(404, '과목을 찾을 수 없습니다');
    return lessons()
      .filter((l) => l.courseId === courseId)
      .map(advance)
      .filter((l) => u.role === 'teacher' || OPEN_TO_STUDENTS.includes(l.status))
      .sort((a, b) => a.sessionNo - b.sessionNo)
      .map(toSummary);
  },

  async createLesson(courseId: string, input: NewLessonInput): Promise<Lesson> {
    await delay(700);
    const u = currentUser();
    if (u.role !== 'teacher' || !canAccessCourse(u, courseId)) throw fail(403, '교사만 할 수 있습니다');
    if (!/\.pdf$/i.test(input.file.name)) throw fail(400, 'PDF 파일만 올릴 수 있습니다');
    if (lessons().some((l) => l.courseId === courseId && l.sessionNo === input.sessionNo))
      throw fail(409, `${input.sessionNo}회차가 이미 있습니다`);
    const l: MockLesson = {
      id: newId(),
      courseId,
      sessionNo: input.sessionNo,
      title: input.title,
      classDate: input.classDate,
      status: 'uploaded',
      progress: 0,
      currentPage: 1,
      pages: rawPages(),
    };
    saveLessons([...lessons(), l]);
    return forViewer(l, u);
  },

  async generateLesson(lessonId: string): Promise<LessonSummary> {
    await delay();
    const l = findLesson(lessonId, { teacherOnly: true });
    if (l.status === 'processing') throw fail(409, '재구성 작업 중입니다. 끝난 뒤 다시 시도해 주세요');
    if (!['uploaded', 'review'].includes(l.status)) throw fail(409, '승인된 회차는 다시 생성할 수 없습니다');
    return toSummary(patchLesson(lessonId, { status: 'processing', progress: 0, generateStartedAt: Date.now() }));
  },

  async getLesson(id: string): Promise<Lesson> {
    await delay();
    return forViewer(findLesson(id), currentUser());
  },

  async updateLesson(lesson: Lesson): Promise<Lesson> {
    await delay();
    findLesson(lesson.id, { teacherOnly: true });
    return patchLesson(lesson.id, { pages: lesson.pages });
  },

  async approveLesson(id: string): Promise<Lesson> {
    await delay();
    const l = findLesson(id, { teacherOnly: true });
    if (['uploaded', 'processing'].includes(l.status)) throw fail(409, '재구성을 마친 뒤 승인할 수 있습니다');
    if (['live', 'ended'].includes(l.status)) throw fail(409, '이미 수업이 시작된 회차입니다');
    return patchLesson(id, {
      status: 'approved',
      pages: l.pages.map((p) => (p.image ? { ...p, image: { ...p.image, approved: true } } : p)),
    });
  },

  async explainTerm(_lessonId: string, _pageIndex: number, word: string): Promise<{ meaning: string }> {
    await delay(700);
    const dict: Record<string, string> = {
      이산화탄소: '숨을 내쉴 때 나오는, 눈에 보이지 않는 기체',
      '이산화 탄소': '숨을 내쉴 때 나오는, 눈에 보이지 않는 기체',
      산소: '우리가 숨 쉴 때 필요한 기체',
      양분: '생물이 살고 자라는 데 필요한 영양',
      방출: '안에 있던 것을 밖으로 내보내는 것',
      합성: '여러 가지를 합쳐 새로운 것을 만드는 것',
      뿌리털: '뿌리 끝에 난 아주 가는 털. 물을 빨아들여요',
      공변세포: '기공을 열고 닫는 두 개의 세포',
    };
    return { meaning: dict[word] ?? `(AI 예시) '${word}'를 쉬운 말로 풀어 쓴 뜻` };
  },

  async generateImage(lessonId: string, pageIndex: number, prompt: string): Promise<LessonPage> {
    await delay(1000);
    const l = findLesson(lessonId, { teacherOnly: true });
    const page = l.pages.find((p) => p.index === pageIndex);
    if (!page) throw fail(404, '페이지를 찾을 수 없습니다');
    const usePrompt = prompt.trim() || page.image?.prompt || '';
    if (!usePrompt) throw fail(400, 'AI 제안 프롬프트가 없습니다. prompt를 직접 입력해 주세요');
    const updated: LessonPage = {
      ...page,
      image: { url: img(usePrompt), reason: page.image?.reason || '교사가 직접 요청', prompt: usePrompt, approved: l.status !== 'review' },
    };
    patchLesson(lessonId, { pages: l.pages.map((p) => (p.index === pageIndex ? updated : p)) });
    return updated;
  },

  async deleteImage(lessonId: string, pageIndex: number): Promise<LessonPage> {
    await delay();
    const l = findLesson(lessonId, { teacherOnly: true });
    const page = l.pages.find((p) => p.index === pageIndex);
    if (!page) throw fail(404, '페이지를 찾을 수 없습니다');
    const updated = { ...page, image: undefined };
    patchLesson(lessonId, { pages: l.pages.map((p) => (p.index === pageIndex ? updated : p)) });
    return updated;
  },

  // 수업 진행
  async startLesson(id: string): Promise<LessonSummary> {
    await delay();
    const l = findLesson(id, { teacherOnly: true });
    if (l.status === 'live') return toSummary(l);
    if (!['approved', 'ended'].includes(l.status)) throw fail(409, '승인한 회차만 수업을 시작할 수 있습니다');
    const currentPage = l.status === 'approved' ? 1 : l.currentPage;
    const updated = patchLesson(id, { status: 'live', currentPage });
    broadcast(id, { type: 'lesson_started', pageIndex: currentPage });
    return toSummary(updated);
  },

  async endLesson(id: string): Promise<LessonSummary> {
    await delay();
    const l = findLesson(id, { teacherOnly: true });
    if (l.status === 'ended') return toSummary(l);
    if (l.status !== 'live') throw fail(409, '진행 중인 수업이 아닙니다');
    const updated = patchLesson(id, { status: 'ended' });
    broadcast(id, { type: 'lesson_ended' });
    return toSummary(updated);
  },

  async getPageView(lessonId: string, pageIndex: number): Promise<PageLiveView> {
    await delay(100);
    const l = findLesson(lessonId);
    const c = captions()[lessonId]?.[pageIndex] ?? { items: [], hardWords: [] };
    return { pageIndex, teacherPage: getTeacherPage(lessonId, l.currentPage), lessonStatus: l.status, ...c };
  },

  /** 목 모드 전용: 교사 말을 받아 그 페이지 자막 전체를 돌려줌 (실서버의 page_update 흉내) */
  addTranscript(lessonId: string, pageIndex: number, text: string): PageCaptions | null {
    const l = lessons().find((x) => x.id === lessonId);
    if (!l || l.status !== 'live') return null;
    const all = captions();
    const page = all[lessonId]?.[pageIndex] ?? { items: [], hardWords: [] };
    const next: PageCaptions = { ...page, items: [...page.items, toCaption(text)] };
    all[lessonId] = { ...(all[lessonId] ?? {}), [pageIndex]: next };
    save(KEYS.captions, all);
    return next;
  },

  // 퀴즈
  async createQuiz(lessonId: string): Promise<QuizItem[]> {
    await delay(1500);
    const l = findLesson(lessonId, { teacherOnly: true });
    const all = quizzes();
    if (!all[lessonId]) {
      if (!OPEN_TO_STUDENTS.includes(l.status)) throw fail(409, '승인한 회차만 퀴즈를 만들 수 있습니다');
      all[lessonId] = sampleQuiz;
      save(KEYS.quizzes, all);
    }
    return all[lessonId];
  },

  async getQuiz(lessonId: string): Promise<QuizItem[] | null> {
    await delay();
    const u = currentUser();
    findLesson(lessonId);
    const qs = quizzes()[lessonId];
    if (!qs) return null;
    // 학생에게는 정답·해설을 주지 않음 (백엔드와 같게)
    return u.role === 'teacher' ? qs : qs.map(({ answer: _a, explanation: _e, ...q }) => q);
  },

  async submitQuiz(lessonId: string, answers: QuizAnswer[]): Promise<QuizResult> {
    await delay(500);
    const u = currentUser();
    findLesson(lessonId);
    const qs = quizzes()[lessonId];
    if (!qs) throw fail(404, '아직 퀴즈가 없습니다');
    const results = qs.map((q) => {
      const answer = answers.find((a) => a.questionId === q.id)?.answer ?? null;
      return { questionId: q.id, answer, correct: answer === q.answer, correctAnswer: q.answer, explanation: q.explanation, pageIndex: q.pageIndex };
    });
    const result: QuizResult = {
      score: results.filter((r) => r.correct).length,
      total: results.length,
      submittedAt: new Date().toISOString(),
      results,
    };
    const key = `${lessonId}:${u.id}`;
    const all = load<Record<string, QuizResult[]>>(KEYS.attempts, {});
    all[key] = [result, ...(all[key] ?? [])];
    save(KEYS.attempts, all);
    return result;
  },

  async myQuizResults(lessonId: string): Promise<QuizResult[]> {
    await delay(150);
    const u = currentUser();
    return load<Record<string, QuizResult[]>>(KEYS.attempts, {})[`${lessonId}:${u.id}`] ?? [];
  },

  // 챗봇
  async askChat(lessonId: string, message: string): Promise<ChatReply> {
    await delay(600);
    const u = currentUser();
    findLesson(lessonId);
    const reply: ChatReply =
      message.includes('광합성') || message.includes('엽록체')
        ? { answer: '광합성은 식물이 햇빛으로 양분을 만드는 일이에요. 잎 속 엽록체에서 일어나요.', relatedPage: 2 }
        : { answer: '이건 오늘 수업과 다른 이야기예요. 수업 내용에서 궁금한 걸 물어봐 줄래요?' };
    const key = `${lessonId}:${u.id}`;
    const all = load<Record<string, ChatMessage[]>>(KEYS.chats, {});
    all[key] = [...(all[key] ?? []), { from: 'me', text: message }, { from: 'bot', text: reply.answer, relatedPage: reply.relatedPage }];
    save(KEYS.chats, all);
    return reply;
  },

  async getChatHistory(lessonId: string): Promise<ChatMessage[]> {
    await delay(150);
    const u = currentUser();
    return load<Record<string, ChatMessage[]>>(KEYS.chats, {})[`${lessonId}:${u.id}`] ?? [];
  },

  // 필기
  async getAnnotations(lessonId: string): Promise<Record<number, Stroke[]>> {
    await delay(100);
    const key = `${lessonId}:${currentUser().id}`;
    return load<Record<string, Record<number, Stroke[]>>>(KEYS.annotations, {})[key] ?? {};
  },
  async saveAnnotation(lessonId: string, pageIndex: number, strokes: Stroke[]): Promise<void> {
    const key = `${lessonId}:${currentUser().id}`;
    const all = load<Record<string, Record<number, Stroke[]>>>(KEYS.annotations, {});
    const mine = { ...(all[key] ?? {}) };
    if (strokes.length) mine[pageIndex] = strokes;
    else delete mine[pageIndex];
    save(KEYS.annotations, { ...all, [key]: mine });
  },
};
