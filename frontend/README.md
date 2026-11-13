# 천천히 — 프론트엔드

React 19 + Vite + TypeScript + React Router. 기능 정의는 상위 폴더의 `최종_기능_정리.md`,
백엔드 연동은 백엔드 저장소(sinyunju/AXEDU)의 README와 `/docs`를 따릅니다.

## 실행

```bash
npm install
cp .env.example .env.local   # 처음 한 번
npm run dev                  # http://localhost:5173 (같은 Wi-Fi 기기는 http://PC의IP:5173)
```

| 모드 | `.env.local` | 설명 |
|---|---|---|
| 목 모드 (기본) | `VITE_USE_MOCK=true` | 백엔드 없이 브라우저 localStorage로 모든 화면 동작 |
| 실서버 | `VITE_USE_MOCK=false`, `VITE_API_BASE_URL`, `VITE_WS_BASE_URL` | FastAPI 백엔드에 연결 |

목 데이터를 초기화하려면 브라우저 개발자 도구에서 localStorage의 `mock.*` 키를 지웁니다.

## 서비스 흐름

```
선생님: 로그인 → 과목 개설(초대 코드 발급) → 회차 추가: PDF + 회차 번호 + 제목 + 날짜
        → AI 변환(진행률 표시) → 쉬운 문장·어려운 말·이미지 검토 → 승인(학생 공개)
        → 수업 화면(들어가면 수업 시작) → 페이지 넘기며 설명(음성 인식) → 수업 끝내기 → 퀴즈 만들기

학생:   로그인 → 초대 코드로 과목 참여 → 승인된 회차 들어가기
        → 쉬운 문장(왼쪽) + 그림·선생님 설명 자막(오른쪽) → 확인 문제 제출·채점 / 챗봇
```

회차 상태: `uploaded`(변환 전) → `generating`(AI 변환 중) → `ready`(검토 필요) → `approved`(준비 완료) → `live`(수업 중) → `ended`(수업 끝, 다시 시작 가능)

## 목 모드로 시험하기

백엔드 `scripts/seed.py`와 같은 계정·과목입니다.

- 선생님 `teacher1`(김선생), 학생 `student1`~`student3`(이학생·박학생·최학생), 비밀번호 모두 `pass1234`
- 과목 "과학", 초대 코드 `DEMO01` (학생 3명 등록됨)
- 회차: 1회차 광합성(승인됨, 퀴즈 있음) · 2회차 식물의 호흡(검토 필요) · 3회차 광합성과 호흡 비교(변환 전)

**수업 중 화면**

1. 탭 A: `teacher1` → 과목 → 1회차 **수업 시작** (들어가면 자동으로 시작)
2. 탭 B(**같은 브라우저**의 새 탭): `student1` → 과목 → 1회차 들어가기
3. 탭 A에서 설명을 입력하면 탭 B에 자막이 쌓이고, 다음 페이지(▶)를 누르면 탭 B에 "선생님은 지금 2쪽 · 따라가기"가 떠요.
   - "지금부터…/이제…"로 시작하면 흐름 안내(구분선), "과제/준비물/가져와"가 들어가면 과제 상자로 보여요 (목 모드 흉내).
4. 탭 A **수업 끝내기** → **퀴즈 만들기**, 탭 B에는 "수업이 끝났어요" 안내가 떠요.

로그인 토큰은 탭마다 따로 저장(sessionStorage)되어 두 탭이 서로 다른 계정으로 로그인할 수 있습니다.
목 모드의 실시간 연결(BroadcastChannel)은 같은 브라우저의 탭끼리만 됩니다.

## 실서버(백엔드) 연동

### 연결 방법

1. 백엔드 실행 (백엔드 README "로컬 실행" — seed 포함)
2. `.env.local`에서 `VITE_USE_MOCK=false`
3. 휴대폰·태블릿에서 접속하려면
   - `VITE_API_BASE_URL=http://PC의IP:8000`, `VITE_WS_BASE_URL=ws://PC의IP:8000`
   - 백엔드 `.env`의 `FRONTEND_ORIGINS`에 `http://PC의IP:5173` 추가 (안 하면 CORS로 막힘)
4. 스키마 타입 다시 만들기: `npm run gen:api` → `src/api/backend.d.ts`

> `src/api/backend.d.ts`는 실행 중인 백엔드의 `/openapi.json`으로 만든 파일입니다 (`npm run gen:api`).
> 백엔드 스키마가 바뀌면 다시 만들고 `npm run build`가 통과하는지 확인하세요. 실패하면 `src/api/real.ts`의 변환을 고치면 됩니다.

### 구조

```
src/api/
  backend.d.ts   백엔드 스키마 타입 (openapi-typescript 형식)
  real.ts        실서버 어댑터: 백엔드 형식 ↔ 화면 형식 변환은 모두 여기서
  mock.ts        목 구현 (real.ts와 같은 함수·같은 동작)
  realtime.ts    WebSocket (실서버) / BroadcastChannel (목)
  http.ts        fetch 래퍼: Bearer 토큰, {detail} 오류 꺼내기, /files 주소 변환
  types.ts       화면이 쓰는 형식
  index.ts       VITE_USE_MOCK에 따라 real/mock 선택
```

### 변환 규칙 (real.ts)

| 화면 | 백엔드 |
|---|---|
| `User.username` | `login_id` (로그인 응답엔 없어서 `/auth/me`로 받음) |
| 로그인 토큰 | `access_token` |
| 회원가입 | `POST /auth/signup` (토큰 없음) → 바로 `POST /auth/login` |
| `Course.subject` / `joinCode` | `description` / `invite_code` (학생에겐 null) |
| 회차 목록 | `GET /courses/{id}`의 `lessons` |
| 회차 상태 `uploaded·processing·review·approved·live·ended` | `uploaded·generating·ready·approved·live·ended` |
| `Lesson.sessionNo` / `classDate` | `session_no` / `class_date` (날짜만, 시간 없음) |
| `LessonPage.easyText` (한 줄 = 한 문장) | `easy_sentences: string[]` |
| `LessonPage.terms` | `hard_words` |
| `LessonPage.originalText` / `originalImageUrl` | `source_text`(교사만) / `image_url` |
| `LessonPage.image` | `generated_image_url` + `image_suggestion` |
| 이미지·페이지 주소 | `/files/...` 앞에 `VITE_API_BASE_URL`을 붙임 |
| 검토 저장 | 바뀐 페이지만 `PUT /lessons/{id}/pages/{n}` |
| 퀴즈 채점 | 학생은 정답을 받지 않음 → `POST /lessons/{id}/quiz/attempts` 결과로 표시 |
| 챗봇 | `{message}` → `answer.content`, `answer.related_page` |
| 오류 문구 | `{detail}` (문자열 또는 입력 검증 배열의 `msg`) |

### WebSocket (realtime.ts)

- `ws(s)://…/ws/lessons/{id}?token=<access_token>`, 25초마다 `ping`
- 보냄: `page_change {page_no}`, `transcript {page_no, text, final: true}` (음성 인식 확정 문장만)
- 받음: `teacher_page`, `page_update`(그 페이지 자막을 **통째로 교체**, 페이지별로 보관), `lesson_started`, `lesson_ended`, `ack`, `error`, `pong`
- 자막 종류: `content` 말풍선 / `flow` 구분선·작은 글씨 / `notice` 강조 상자 + "과제" 배지 (자막 시각은 표시 안 함)
- 4401/4403/4404로 닫히면 재연결하지 않고 안내 (4401은 로그아웃 후 로그인 화면으로). 그 밖의 끊김은 1.5초 뒤 재연결

### 실서버 모드에서 숨기는 기능 (`src/config.ts`의 `features`)

백엔드에 API가 없어서 목 모드에서만 보입니다. API가 생기면 값을 바꾸고 `real.ts`에 연결하세요.

| 기능 | 키 |
|---|---|
| 슈퍼스쿨 로그인·계정 연동 | `superschool` |
| 메인 화면 캘린더 | `calendar` |
| 이름·이메일 수정, 프로필 사진, 비밀번호 변경 | `profileEdit` |
| 단어를 넣으면 AI가 뜻 채우기 | `explainTerm` |

## 화면 테마

`<html data-theme="blue|pink|yellow|dark">`, 값이 없으면 기기 설정(라이트=파랑, 다크=다크).
선택은 기기마다 localStorage(`pref.theme`)에 저장됩니다. 색은 `src/index.css` 맨 위 토큰만 씁니다.

## 라우트

| 경로 | 역할 | 화면 |
|---|---|---|
| `/` | 공개 | 시작 (로그인 상태면 역할별 첫 화면으로) |
| `/login`, `/signup` | 공개 | 로그인 / 회원가입 |
| `/settings?tab=profile\|appearance\|links` | 로그인 | 내 정보 / 화면 테마 / 계정 연동(목 모드) |
| `/teacher` | 교사 | 내 과목, 과목 개설 (목 모드는 캘린더 포함) |
| `/teacher/courses/:courseId` | 교사 | 초대 코드, 회차 목록, 회차 추가(PDF) |
| `/teacher/lessons/:lessonId/review` | 교사 | AI 변환 진행 → 검토·수정·승인 |
| `/teacher/lessons/:lessonId/live` | 교사 | 수업 시작·진행·끝내기, 퀴즈 만들기 |
| `/student` | 학생 | 내 과목, 초대 코드로 참여 |
| `/student/courses/:courseId` | 학생 | 열린 회차 목록 |
| `/class/:lessonId` | 학생 | 쉬운 문장 + 그림 + 선생님 설명 자막 |
| `/class/:lessonId/quiz`, `/chat` | 학생 | 확인 문제(제출·채점), 챗봇(대화 기록 포함) |

## 추후 계획

- **과목 참여 학생 확인 (교사)** — 백엔드에 `GET /courses/{id}/students`가 이미 있어서 화면만 붙이면 됩니다.
  슈퍼스쿨 반 명단 자동 등록은 슈퍼스쿨 연동이 가능해지면 함께. 학생별 학습 기록·진단성 정보는 보여주지 않음 (낙인 방지).
- 백엔드 API가 생기면: 프로필 수정·사진·비밀번호, 슈퍼스쿨, 캘린더, 낱말 뜻 AI 생성
