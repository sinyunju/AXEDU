// 실서버(FastAPI) 연동. 백엔드 형식(backend.d.ts) ↔ 화면 형식(types.ts) 변환은 모두 여기서 합니다.
import type { components } from './backend';
import { ApiError, fileUrl, http } from './http';
import type {
  AuthResponse,
  CalendarResponse,
  ChatMessage,
  ChatReply,
  Course,
  Lesson,
  LessonPage,
  LessonStatus,
  LessonSummary,
  NewLessonInput,
  PageLiveView,
  ProfileInput,
  QuizAnswer,
  QuizItem,
  QuizResult,
  Role,
  SignupInput,
  Stroke,
  Term,
  User,
} from './types';

type S = components['schemas'];

const post = (body?: unknown) => ({ method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });
const notSupported = (what: string) => () => Promise.reject(new ApiError(501, `${what}은(는) 아직 서버에서 지원하지 않아요`));

// ---------- 변환 ----------

const STATUS: Record<S['LessonStatus'], LessonStatus> = {
  uploaded: 'uploaded',
  generating: 'processing',
  ready: 'review',
  approved: 'approved',
  live: 'live',
  ended: 'ended',
};

function toUser(u: S['UserOut'] | S['UserBrief']): User {
  return { id: String(u.id), role: u.role, username: u.login_id, name: u.name, superschoolLinked: false };
}

function toCourse(c: S['CourseOut'], lessonCount?: number): Course {
  return {
    id: String(c.id),
    name: c.name,
    subject: c.description,
    joinCode: c.invite_code ?? undefined,
    teacherName: c.teacher_name,
    lessonCount: lessonCount ?? c.lesson_count, // 학생에게는 볼 수 있는 회차 수
  };
}

function toSummary(l: S['LessonBrief'] | S['LessonOut'], courseId: string): LessonSummary {
  return {
    id: String(l.id),
    courseId,
    sessionNo: l.session_no,
    title: l.title,
    classDate: l.class_date ?? undefined,
    status: STATUS[l.status],
    progress: l.progress,
    pageCount: 'page_count' in l ? l.page_count : undefined,
  };
}

const toTerms = (words: S['HardWord'][]): Term[] => words.map((w) => ({ word: w.word, meaning: w.meaning }));

function toPage(p: S['PageOut']): LessonPage {
  const s = p.image_suggestion;
  const image =
    p.generated_image_url || s?.needed
      ? {
          url: fileUrl(p.generated_image_url),
          reason: s?.reason ?? '',
          prompt: s?.prompt || undefined,
          approved: p.approved,
        }
      : undefined;
  return {
    index: p.page_no,
    originalImageUrl: fileUrl(p.image_url),
    originalText: p.source_text ?? '',
    easyText: p.easy_sentences.join('\n'),
    terms: toTerms(p.hard_words),
    image,
  };
}

function toLesson(l: S['LessonDetail']): Lesson {
  return {
    ...toSummary(l, String(l.course_id)),
    currentPage: l.current_page,
    pages: l.pages.map(toPage),
  };
}

/** 화면의 쉬운 문장(한 줄에 한 문장) → 백엔드 easy_sentences */
const toSentences = (easyText: string) =>
  easyText
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);

function toPageUpdate(p: LessonPage): S['PageUpdate'] {
  return {
    easy_sentences: toSentences(p.easyText),
    hard_words: p.terms.filter((t) => t.word.trim()).map((t) => ({ word: t.word.trim(), meaning: t.meaning.trim() })),
  };
}

function toQuizItem(q: S['QuizQuestionOut']): QuizItem {
  return {
    id: String(q.id),
    type: q.type === 'ox' ? 'ox' : 'choice',
    question: q.question,
    choices: q.choices,
    pageIndex: q.page_no ?? undefined,
  };
}

function toQuizResult(a: S['AttemptOut']): QuizResult {
  return {
    score: a.score,
    total: a.total,
    submittedAt: a.submitted_at,
    results: a.results.map((r) => ({
      questionId: String(r.question_id),
      answer: r.answer,
      correct: r.correct,
      correctAnswer: r.correct_answer,
      explanation: r.explanation,
      pageIndex: r.page_no ?? undefined,
    })),
  };
}

// 검토 화면 저장 시 바뀐 페이지만 PUT 하려고, 마지막으로 받은 페이지 내용을 기억
const savedPages = new Map<string, Map<number, string>>();
function remember(lesson: Lesson) {
  savedPages.set(lesson.id, new Map(lesson.pages.map((p) => [p.index, JSON.stringify(toPageUpdate(p))])));
  return lesson;
}

// ---------- API ----------

export const realApi = {
  // 인증
  async login(username: string, password: string): Promise<AuthResponse> {
    const res = await http<S['LoginResponse']>('/auth/login', post({ login_id: username, password } satisfies S['LoginRequest']));
    // 로그인 응답의 user에 login_id가 있으면 그대로 쓰고, 예전 백엔드처럼 없으면 /auth/me로 받음
    const user = res.user.login_id ? res.user : await http<S['UserOut']>('/auth/me', { token: res.access_token });
    return { token: res.access_token, user: toUser(user) };
  },
  async signup(input: SignupInput): Promise<AuthResponse> {
    const body: S['SignupRequest'] = { login_id: input.username, password: input.password, name: input.name, role: input.role };
    await http<S['UserOut']>('/auth/signup', post(body)); // 가입은 토큰을 주지 않음 → 바로 로그인
    return realApi.login(input.username, input.password);
  },
  me: async (): Promise<User> => toUser(await http<S['UserOut']>('/auth/me')),

  // 백엔드에 없는 기능 (화면에서는 features로 숨김)
  superschoolAuthorizeUrl: (_mode: 'login' | 'link', _role?: Role): string => '/login',
  superschoolLogin: notSupported('슈퍼스쿨 로그인') as (code: string) => Promise<AuthResponse>,
  linkSuperschool: notSupported('슈퍼스쿨 연동') as (code: string) => Promise<User>,
  unlinkSuperschool: notSupported('슈퍼스쿨 연동') as () => Promise<User>,
  updateMe: notSupported('내 정보 수정') as (input: ProfileInput) => Promise<User>,
  uploadAvatar: notSupported('프로필 사진') as (file: Blob) => Promise<{ avatarUrl: string }>,
  changePassword: notSupported('비밀번호 변경') as (current: string, next: string) => Promise<void>,
  getCalendar: notSupported('일정') as (from: string, to: string) => Promise<CalendarResponse>,
  explainTerm: notSupported('낱말 뜻 만들기') as (lessonId: string, pageIndex: number, word: string) => Promise<{ meaning: string }>,

  // 과목
  listCourses: async (): Promise<Course[]> => (await http<S['CourseOut'][]>('/courses')).map((c) => toCourse(c)),
  async createCourse(name: string, subject: string): Promise<Course> {
    return toCourse(await http<S['CourseOut']>('/courses', post({ name, description: subject } satisfies S['CourseCreate'])), 0);
  },
  async getCourse(id: string): Promise<Course> {
    const c = await http<S['CourseDetail']>(`/courses/${id}`);
    return toCourse(c, c.lessons.length);
  },
  async joinCourse(code: string): Promise<Course> {
    const res = await http<S['JoinResponse']>('/courses/join', post({ invite_code: code.trim().toUpperCase() } satisfies S['JoinRequest']));
    return toCourse(res.course);
  },

  // 회차
  /** 회차 목록은 과목 상세(GET /courses/{id}) 응답에서 꺼냄 */
  async listLessons(courseId: string): Promise<LessonSummary[]> {
    const c = await http<S['CourseDetail']>(`/courses/${courseId}`);
    return c.lessons.map((l) => toSummary(l, courseId));
  },
  /** PDF·회차 번호·제목·날짜를 multipart로 한 번에 올림 (AI 변환은 generateLesson으로 따로 시작) */
  async createLesson(courseId: string, input: NewLessonInput): Promise<Lesson> {
    const form = new FormData();
    form.append('file', input.file);
    form.append('session_no', String(input.sessionNo));
    form.append('title', input.title);
    if (input.classDate) form.append('class_date', input.classDate);
    return remember(toLesson(await http<S['LessonDetail']>(`/courses/${courseId}/lessons`, { method: 'POST', body: form })));
  },
  /** AI 변환 시작 (202). 진행률은 getLesson의 progress로 확인 */
  generateLesson: async (lessonId: string): Promise<LessonSummary> => {
    const l = await http<S['LessonOut']>(`/lessons/${lessonId}/generate`, post());
    return toSummary(l, String(l.course_id));
  },
  getLesson: async (id: string): Promise<Lesson> => remember(toLesson(await http<S['LessonDetail']>(`/lessons/${id}`))),
  /** 검토 내용 저장: 바뀐 페이지만 PUT /lessons/{id}/pages/{n} */
  async updateLesson(lesson: Lesson): Promise<Lesson> {
    const saved = savedPages.get(lesson.id) ?? new Map<number, string>();
    for (const page of lesson.pages) {
      const body = toPageUpdate(page);
      if (saved.get(page.index) === JSON.stringify(body)) continue;
      await http<S['PageOut']>(`/lessons/${lesson.id}/pages/${page.index}`, { method: 'PUT', body: JSON.stringify(body) });
      saved.set(page.index, JSON.stringify(body));
    }
    savedPages.set(lesson.id, saved);
    return lesson;
  },
  approveLesson: async (id: string): Promise<Lesson> =>
    remember(toLesson(await http<S['LessonDetail']>(`/lessons/${id}/approve`, post()))),
  /** 이미지 생성. prompt를 비우면 AI 제안을 씀 */
  generateImage: async (lessonId: string, pageIndex: number, prompt: string): Promise<LessonPage> =>
    toPage(await http<S['PageOut']>(`/lessons/${lessonId}/pages/${pageIndex}/image`, post({ prompt: prompt.trim() || null } satisfies S['ImageRequest']))),
  deleteImage: async (lessonId: string, pageIndex: number): Promise<LessonPage> =>
    toPage(await http<S['PageOut']>(`/lessons/${lessonId}/pages/${pageIndex}/image`, { method: 'DELETE' })),

  // 수업 진행
  startLesson: async (id: string): Promise<LessonSummary> => {
    const l = await http<S['LessonOut']>(`/lessons/${id}/start`, post());
    return toSummary(l, String(l.course_id));
  },
  endLesson: async (id: string): Promise<LessonSummary> => {
    const l = await http<S['LessonOut']>(`/lessons/${id}/end`, post());
    return toSummary(l, String(l.course_id));
  },
  async getPageView(lessonId: string, pageIndex: number): Promise<PageLiveView> {
    const v = await http<S['PageView']>(`/lessons/${lessonId}/pages/${pageIndex}`);
    return {
      pageIndex: v.page_no,
      teacherPage: v.teacher_page,
      lessonStatus: STATUS[v.lesson_status],
      items: v.easy_transcript.map((c) => ({ text: c.text, kind: c.type })),
      hardWords: toTerms(v.transcript_hard_words),
    };
  },

  // 퀴즈
  /** 교사: 퀴즈 만들기 (이미 있으면 기존 것). 10~25초 걸림 */
  createQuiz: async (lessonId: string): Promise<QuizItem[]> =>
    (await http<S['QuizOut']>(`/lessons/${lessonId}/quiz`, post())).questions.map(toQuizItem),
  /** 아직 퀴즈가 없으면 null */
  async getQuiz(lessonId: string): Promise<QuizItem[] | null> {
    try {
      return (await http<S['QuizOut']>(`/lessons/${lessonId}/quiz`)).questions.map(toQuizItem);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }
  },
  submitQuiz: async (lessonId: string, answers: QuizAnswer[]): Promise<QuizResult> =>
    toQuizResult(
      await http<S['AttemptOut']>(
        `/lessons/${lessonId}/quiz/attempts`,
        post({ answers: answers.map((a) => ({ question_id: Number(a.questionId), answer: a.answer })) } satisfies S['AttemptCreate']),
      ),
    ),
  myQuizResults: async (lessonId: string): Promise<QuizResult[]> =>
    (await http<S['AttemptOut'][]>(`/lessons/${lessonId}/quiz/attempts/me`)).map(toQuizResult),

  // 필기 (자기 것만)
  /** 페이지 번호 → 획 목록 (필기가 있는 페이지만) */
  async getAnnotations(lessonId: string): Promise<Record<number, Stroke[]>> {
    const res = await http<S['AnnotationList']>(`/lessons/${lessonId}/annotations`);
    return Object.fromEntries(res.pages.map((p) => [p.page_no, p.strokes as Stroke[]]));
  },
  /** 그 페이지 필기 전체를 덮어씀. 빈 배열이면 삭제. keepalive는 화면을 떠나는 중에도 보내기 위함 */
  async saveAnnotation(lessonId: string, pageIndex: number, strokes: Stroke[], keepalive = false): Promise<void> {
    await http<S['AnnotationOut']>(`/lessons/${lessonId}/annotations/${pageIndex}`, {
      method: 'PUT',
      body: JSON.stringify({ strokes } satisfies S['AnnotationIn']),
      keepalive,
    });
  },

  // 챗봇
  async askChat(lessonId: string, message: string): Promise<ChatReply> {
    const res = await http<S['ChatExchange']>(`/lessons/${lessonId}/chat`, post({ message } satisfies S['ChatRequest']));
    return { answer: res.answer.content, relatedPage: res.answer.related_page ?? undefined };
  },
  getChatHistory: async (lessonId: string): Promise<ChatMessage[]> =>
    (await http<S['ChatMessageOut'][]>(`/lessons/${lessonId}/chat`)).map((m) => ({
      from: m.role === 'user' ? 'me' : 'bot',
      text: m.content,
      relatedPage: m.related_page ?? undefined,
    })),
};

export type Api = typeof realApi;
