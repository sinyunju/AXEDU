# 토끼와 거북이 백엔드 구현 명세 (v2: 로그인·과목 구조 추가)

> 이 문서를 프로젝트 루트에 `CLAUDE.md`로 두고 작업할 것.
> 한 번에 다 만들지 말고 "8. 구현 순서"의 단계별로 진행하고, 단계마다 테스트를 통과시킨 뒤 다음으로 넘어갈 것.
> v1 대비 변경점: 로그인(교사/학생 역할), 과목(Course) → 회차별 수업(Lesson) 구조, 학생 개인별 챗봇·문제 기록. 수업 코드+닉네임 입장 방식은 폐지.

## 1. 서비스 개요
경계선 지능(느린 학습자) 학생이 일반 학급 수업을 놓치지 않도록 돕는 웹 서비스.
- 교사와 학생은 각자 계정으로 로그인한다.
- 교사는 과목을 만들고, 과목 안에 수업 회차별로 수업 자료(PDF)를 올린다. AI가 페이지별로 쉬운 문장으로 재구성하고 이해가 어려운 부분에 이미지를 제안·생성한다. 교사가 검토·승인한다.
- 학생은 과목 초대 코드로 과목에 등록하고, 과목의 수업 회차 목록에서 자료를 본다.
- 수업 중: 교사가 페이지를 넘길 때마다 교사 발화(STT 텍스트)를 해당 페이지에 쌓고, 실시간으로 쉬운 문장으로 바꿔 학생에게 보낸다. 학생은 페이지를 자유롭게 이동하며, "선생님은 지금 N페이지" 정보만 받는다.
- 수업 후: 이해도 확인 문제를 풀고(학생별 기록), 해당 수업 내용을 중심으로 답하는 챗봇을 학생 개인별로 사용한다(학생별 대화 기록).

## 2. 기술 스택
- Python 3.12, FastAPI, Uvicorn
- DB: SQLite + SQLModel (해커톤용. 추후 Postgres 교체 가능하도록 세션 주입 구조로)
- 인증: 아이디+비밀번호 로그인, 비밀번호는 bcrypt 해시 저장, JWT access token(Bearer). 역할(role)은 `teacher | student`
  - 해커톤 범위: 이메일 인증, 비밀번호 찾기, 소셜/학교 계정 연동은 하지 않음
  - 데모용 시드 스크립트 `scripts/seed.py`: 교사 1명, 학생 3명, 과목 1개, 학생 등록까지 생성
- PDF 처리: PyMuPDF (페이지 텍스트 추출 + 페이지 PNG 렌더링)
- LLM / 이미지 생성: `app/ai/` 아래 provider 인터페이스로 분리. 실제 provider는 환경변수로 선택
  - 기본 provider: 안뇽GPT API Gateway (OpenAI 호환). Python `openai` SDK에 `base_url`만 바꿔서 사용
    - `AI_BASE_URL=https://api.baze.co/v1/gateway`, `AI_API_KEY=...` (키는 `.env`에만, 프론트 노출 금지)
    - 모델은 환경변수로 분리: `MODEL_FAST`(실시간 자막, 기본 `gemini-3.5-flash-lite`), `MODEL_MAIN`(재구성·퀴즈·챗봇, 기본 `gemini-3.8-flash`), `MODEL_IMAGE`(기본 `gemini-nano-banana-2.1`)
    - 이미지 생성 엔드포인트는 Gateway 전용 경로(`POST /images/generate/`)이므로 OpenAI SDK의 images API와 형식이 다를 수 있음. 개발자 문서의 요청/응답 형식을 확인해 별도 함수로 구현할 것
  - 예비 provider: Google Gemini API 직접 호출 (Gateway 장애·크레딧 소진 대비)
- `MOCK_AI=true`이면 LLM/이미지 호출 없이 고정 응답을 반환 (API 키 없이 프론트 연동 가능해야 함)
- STT는 프론트(브라우저 Web Speech API)에서 처리. 백엔드는 텍스트만 받는다
- 원본 음성은 저장하지 않는다. 전사 텍스트만 저장한다 (개인정보)
- CORS: 환경변수 `FRONTEND_ORIGINS`(쉼표 구분)로 허용 도메인 설정 (Vercel 배포 도메인 + localhost)
- 설정은 `.env` + pydantic-settings. `.env.example` 제공 (`JWT_SECRET` 포함)

## 3. 데이터 모델
- **User**: id, login_id(고유), password_hash, name, role(`teacher | student`), created_at
- **Course**(과목): id, teacher_id → User, name, description, invite_code(6자리 영숫자, 고유), created_at
- **Enrollment**(수강 등록): id, course_id, student_id → User, joined_at  (course_id+student_id 고유)
- **Lesson**(수업 회차): id, course_id, session_no(회차 번호), title, class_date(nullable),
  status(`uploaded | generating | ready | approved | live | ended`), progress(0~100), current_page, created_at
  (course_id+session_no 고유)
- **Page**: id, lesson_id, page_no, image_path(원본 페이지 PNG), source_text,
  easy_sentences(JSON 리스트), hard_words(JSON: [{word, meaning}]),
  image_suggestion(JSON: {needed: bool, reason, prompt} | null),
  generated_image_path(nullable), approved(bool)
- **Transcript**: id, lesson_id, page_no, text, created_at  (페이지별 교사 발화 조각)
- **PageLive**: lesson_id, page_no, easy_transcript(JSON: [{text, type}]), hard_words(JSON: [{word, meaning}]), updated_at  (실시간 쉬운 자막 결과. type은 `content | flow | notice`, 6절 참고. hard_words는 재접속 시 복원용)
- **Quiz**: id, lesson_id, questions(JSON)  (회차당 1개)
- **QuizAttempt**: id, quiz_id, student_id, answers(JSON), score, submitted_at  (학생별 기록)
- **ChatMessage**: id, lesson_id, student_id, role(`user | assistant`), content, related_page(nullable), created_at  (학생별·회차별 대화 기록)
- **Annotation**(필기): user_id, lesson_id, page_no(셋이 PK), strokes(JSON: [{tool: `pen | highlighter`, color: `#rrggbb`, width, points: [[x, y], ...]}]), updated_at  (교사·학생 각자의 수업 자료 필기. 좌표·굵기는 페이지 크기 기준 0~1 비율)

v1의 Session(수업 코드), Student(닉네임) 모델은 사용하지 않는다. 실시간 수업 상태는 Lesson.status=`live`와 Lesson.current_page로 관리한다.

## 4. REST API
- 모든 응답은 JSON. 에러는 `{"detail": "..."}`.
- 인증이 필요한 API는 `Authorization: Bearer <token>` 헤더 사용.
- 권한 규칙
  - 교사는 **자기 과목**과 그 하위 데이터만 생성·수정·조회 가능
  - 학생은 **등록한 과목**의 수업만 조회 가능하고, 승인된(`approved` 이상) 회차만 보인다
  - 학생은 자기 문제 기록과 자기 챗봇 대화만 볼 수 있다
  - 필기는 교사·학생 모두 자기 것만 보고 고친다
  - 권한 없으면 403, 없는 리소스는 404

### 인증
- `POST /auth/signup` (body: {login_id, password, name, role}) → 사용자 생성
- `POST /auth/login` (body: {login_id, password}) → {access_token, user: {id, name, role}}
- `GET /auth/me` → 현재 사용자

### 과목 (교사)
- `POST /courses` (body: {name, description}) → 과목 생성 + invite_code 발급
- `GET /courses` → 교사: 내가 만든 과목 / 학생: 내가 등록한 과목
- `GET /courses/{course_id}` → 과목 정보 + 회차 목록 (학생에게는 승인된 회차만)
- `GET /courses/{course_id}/students` → 등록 학생 목록 (교사 전용)

### 과목 등록 (학생)
- `POST /courses/join` (body: {invite_code}) → Enrollment 생성

### 수업 회차와 자료 (교사)
- `POST /courses/{course_id}/lessons` (multipart: file=PDF, session_no, title, class_date?) → 페이지 분리, 텍스트 추출, PNG 렌더링 → Lesson 반환
- `POST /lessons/{lesson_id}/generate` → 백그라운드 작업으로 페이지별 재구성 시작. 즉시 202 반환
- `GET /lessons/{lesson_id}` → Lesson + Pages + progress (교사: 전체, 학생: 승인된 내용만)
- `PUT /lessons/{lesson_id}/pages/{page_no}` → 교사가 easy_sentences / hard_words 수정
- `POST /lessons/{lesson_id}/pages/{page_no}/image` (body: {prompt?}) → 이미지 생성 (교사가 직접 지정하거나 AI 제안 prompt 사용)
- `DELETE /lessons/{lesson_id}/pages/{page_no}/image` → 이미지/제안 삭제
- `POST /lessons/{lesson_id}/approve` → 회차 승인 (학생에게 공개)
- `POST /lessons/{lesson_id}/start` → 실시간 수업 시작 (status=`live`)
- `POST /lessons/{lesson_id}/end` → 수업 종료 (status=`ended`)
- 정적 파일: `/files/...` 로 페이지 PNG와 생성 이미지 제공 (해커톤에서는 인증 없이 제공해도 됨. 파일명은 추측하기 어렵게 UUID 사용)

### 학생
- `GET /lessons/{lesson_id}/pages/{page_no}` → 원본 이미지 URL, easy_sentences, hard_words, generated_image URL, 현재까지의 easy_transcript

### 수업 후
- `POST /lessons/{lesson_id}/quiz` → 문제 생성 (교사 전용, 이미 있으면 기존 것 반환)
- `GET /lessons/{lesson_id}/quiz` → 문제 조회 (학생에게는 정답 제외)
- `POST /lessons/{lesson_id}/quiz/attempts` (body: {answers:[{question_id, answer}]}) → 채점 결과 + 해설 저장 후 반환 (학생 본인 기록)
- `GET /lessons/{lesson_id}/quiz/attempts/me` → 내 풀이 기록
- `POST /lessons/{lesson_id}/chat` (body: {message}) → 챗봇 답변 (+ 관련 page_no). 이 학생의 이전 대화(최근 N개)를 문맥으로 사용
- `GET /lessons/{lesson_id}/chat` → 내 대화 기록

### 필기 (교사·학생)
- `GET /lessons/{lesson_id}/annotations` → 내 필기 전체 ({pages: [{page_no, strokes, updated_at}]}, 필기가 있는 페이지만)
- `PUT /lessons/{lesson_id}/annotations/{page_no}` (body: {strokes}) → 그 페이지 내 필기 전체를 덮어씀. 빈 배열이면 삭제
  (한 페이지 최대 1000획·점 5만 개, 한 획 최대 점 5000개. 범위를 벗어난 좌표는 0~1로 자름)

## 5. WebSocket: `/ws/lessons/{lesson_id}?token=<JWT>`
- 브라우저 WebSocket은 헤더를 붙이기 어려우므로 토큰을 쿼리로 받는다. 연결 시 토큰 검증 + 권한 확인(교사: 과목 소유자, 학생: 등록 학생). 실패 시 연결 거부
- 역할은 토큰의 사용자 role로 판단한다 (쿼리로 받지 않음)
- 메시지는 모두 `{"type": "...", ...}` 형식의 JSON

교사 → 서버
- `{"type":"page_change","page_no":5}`
- `{"type":"transcript","page_no":5,"text":"...","final":true}`  (Web Speech API의 확정 결과만 전송. page_no는 그 문장을 **말하기 시작할 때** 보던 페이지)
- `{"type":"pointer","page_no":5,"x":0.42,"y":0.31}`  (레이저 포인터, 0~1 비율. x·y가 null이면 숨김. 저장하지 않고 ack도 보내지 않음)

서버 → 교사·학생 모두 (broadcast, 교사 화면에서도 학생이 받는 자막을 확인할 수 있도록)
- `{"type":"teacher_page","page_no":5}`
- `{"type":"page_update","page_no":5,"easy_transcript":[{"text":"...","type":"content"},{"text":"...","type":"flow"}],"hard_words":[...]}`  (easy_transcript는 그 페이지 자막 전체)
- `{"type":"lesson_started","page_no":1}`  (`POST /lessons/{id}/start` 시. 승인된 회차에 미리 접속해 있던 학생에게 수업 시작을 알림)
- `{"type":"lesson_ended"}`  (`POST /lessons/{id}/end` 시)

서버 → 학생만
- `{"type":"pointer","page_no":5,"x":0.42,"y":0.31}`  (교사 레이저. 학생은 그 페이지를 보고 있을 때만 표시. 숨김은 x·y null)

서버 → 교사
- `{"type":"ack", ...}`, 오류 시 `{"type":"error","detail":"..."}`

요구사항
- 연결 시 현재 상태(teacher_page)를 바로 보내줄 것. 재연결해도 상태가 복원되어야 함
- 연결 관리는 lesson_id별 in-memory ConnectionManager (단일 프로세스 전제. 이 전제를 코드 주석에 명시)
- 클라이언트 ping/pong 또는 주기적 heartbeat로 연결 유지

## 6. 실시간 쉬운 자막 로직
- transcript 수신 → Transcript 저장 → 해당 페이지 버퍼에 누적
- 다음 중 하나가 충족되면 LLM 호출: (a) 마지막 호출 후 15초 경과 + 새 텍스트 있음, (b) page_change 발생(이전 페이지 확정)
- 같은 페이지에 대해 LLM 호출이 동시에 겹치지 않도록 페이지별 lock
- LLM 입력: 페이지 source_text + 해당 페이지의 누적 발화 전체 + 직전 easy_transcript
- LLM 출력(JSON): `{"easy_transcript": [{"text":"...","type":"content"}], "hard_words": [{"word":"","meaning":""}]}`
- 자막 항목 type
  - `content`: 수업 내용 설명
  - `flow`: 수업 흐름 안내 ("지금부터 정리해요", "첫 번째는…", "이제 ○○를 볼 거예요") — 남긴다
  - `notice`: 과제·준비물 안내
  - 단순 이동·주목 멘트("다음 장 넘겨 볼까요", "여기 보세요")는 자막에서 뺀다
- 자막의 모든 문장은 교사가 실제로 한 말에서 나와야 한다. 페이지 글에 있어도 교사가 아직 말하지 않은 내용은 넣지 않는다 (페이지 글은 STT 오타 보정·용어 확인용)
- 결과를 PageLive에 저장하고 `page_update` broadcast

## 7. LLM 작업과 프롬프트 규칙 (공통)
대상: 초등 고학년~중학생 중 경계선 지능(느린 학습자) 학생. 모든 출력은 한국어 JSON.
공통 규칙
- 한 문장은 짧게(대략 25자 이내 권장), 한 문장에 한 가지 내용만
- 어려운 한자어·전문용어는 쉬운 말로 바꾸되, 교과 핵심 용어는 유지하고 hard_words에 쉬운 뜻을 단다
- 원문(페이지 텍스트, 교사 발화)에 없는 사실을 추가하지 않는다 (예외: 챗봇의 기초 질문, 작업 4 참고)
- 학생을 낮추거나 "어렵죠?" 같은 표현을 쓰지 않는다
- 반드시 지정된 JSON 스키마로만 응답. 파싱 실패 시 1회 재시도 후 에러 처리

작업별
1. **페이지 재구성**: source_text → `{easy_sentences[], hard_words[], image_suggestion}`
   - image_suggestion.needed는 추상 개념, 과정·순서, 공간 관계, 여러 요소의 관계처럼 글만으로 이해가 어려운 경우에만 true. 대부분의 페이지는 false
   - prompt는 "글자 없는 단순한 교육용 일러스트"를 기준으로 작성
2. **실시간 자막**: 6절 참고. 수업과 무관한 발화(출석, 생활지도, 잡담)와 단순 이동 멘트는 제외, 수업 흐름 안내는 type=flow로 남김
3. **퀴즈 생성**: 승인된 페이지 내용 + 교사 발화 → 5문항 내외. 유형은 OX와 3지선다만. 각 문항에 page_no, 정답, 쉬운 해설 포함
4. **챗봇**: 해당 회차의 페이지 내용과 교사 발화를 우선 근거로 답변. 질문을 넷으로 나눠 처리한다.
   - 수업 내용으로 답할 수 있는 질문 → 수업 내용으로 답하고 근거 page_no 반환
   - 수업 주제와 바로 이어지는 기초 질문(예: 광합성 수업에서 "광합성은 어디에서 일어나요?") → 수업 내용에 답이 없어도 초등 고학년~중학생 교과서 수준의 확실한 사실로 짧게 답하고, 답과 이어지는 내용이 나온 근거 page_no를 반드시 반환. 근거 페이지를 찾지 못하면 아래 "심화"로 처리(서버에서 강제). 공통 규칙의 "원문에 없는 사실 추가 금지"는 이 경우에만 예외
   - 수업 주제와 관련은 있지만 학년 수준을 넘거나 확실하지 않은 내용 → "오늘 수업에서는 거기까지 나오지 않았어요. 선생님께 물어보면 알려 주실 거예요."
   - 수업과 무관한 질문(다른 과목, 숙제 답, 잡담 등) → "이건 오늘 수업과 다른 이야기예요. 수업 내용을 물어봐 줄래요?"
   - 답변은 짧은 문장 3개 이내. 학생 개인의 이전 대화를 문맥으로 사용

## 8. 구현 순서 (단계마다 동작 확인 후 진행)
1. 프로젝트 골격, 설정, DB 모델, `MOCK_AI` provider, 헬스체크 `GET /health`
2. 인증: 회원가입/로그인/JWT/`/auth/me`, 역할별 권한 의존성(`require_teacher`, `require_student`), 시드 스크립트
3. 과목 생성·조회, 초대 코드로 학생 등록
4. 회차별 PDF 업로드 → 페이지 분리/렌더링 → 조회 API
5. 페이지 재구성 백그라운드 작업 + 진행률 + 교사 수정/승인/이미지 API
6. 수업 시작/종료, 학생 페이지 조회
7. WebSocket(토큰 인증) + 실시간 쉬운 자막 (6절)
8. 퀴즈 생성/학생별 채점 기록
9. 학생별 챗봇
10. 데모용 리플레이 스크립트: `scripts/replay.py`가 미리 준비한 (페이지 번호, 발화 텍스트, 시각) JSON을 읽어 교사 WebSocket 클라이언트처럼 재생

## 9. 테스트와 문서
- pytest로 각 단계의 주요 API 테스트 (MOCK_AI 모드). 특히 권한 테스트: 다른 교사의 과목 접근 403, 미등록 학생 접근 403, 다른 학생 챗봇 기록 조회 불가
- FastAPI 자동 문서(`/docs`)가 프론트 연동 기준이 되도록 모든 요청/응답에 Pydantic 스키마 명시
- README에 로컬 실행 방법, 환경변수, 시드 계정, WebSocket 메시지 예시 정리
