# 쉬운수업 백엔드

경계선 지능(느린 학습자) 학생이 일반 학급 수업을 따라갈 수 있게 돕는 서비스의 백엔드입니다.
교사가 올린 수업 자료(PDF)를 AI가 쉬운 문장으로 바꾸고, 수업 중 교사의 말을 실시간 쉬운 자막으로 학생에게 보내며,
수업 후에는 확인 문제와 수업 범위 챗봇을 학생별로 제공합니다.

- 기술: Python 3.12+ (3.13에서 개발·테스트), FastAPI, SQLite + SQLModel, PyMuPDF, 안뇽GPT API Gateway
- 상세 명세: [CLAUDE.md](CLAUDE.md)
- **API 문서(프론트 연동 기준): 서버 실행 후 http://localhost:8000/docs**

## 로컬 실행

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env              # 필요한 값 수정 (아래 환경변수 참고)
.venv/bin/python -m scripts.seed  # 데모 계정·과목 생성 (여러 번 실행해도 안전)
.venv/bin/uvicorn app.main:app --reload --port 8000
```

- 헬스체크: `GET /health` → `{"status":"ok","mock_ai":true,"mock_image":true,...}`
- 테스트: `.venv/bin/pytest -q` (항상 MOCK 모드 + 임시 DB로 실행, API 키 불필요)

> **서버는 프로세스 하나로만 실행하세요.** WebSocket 연결과 실시간 자막 상태를 메모리에 두기 때문에
> `--workers 2` 이상이나 여러 인스턴스로 띄우면 교사와 학생 메시지가 서로 전달되지 않습니다.
> 같은 DB에 서버를 두 개 띄우는 것도 피하세요 (시작 시 정리 작업이 서로의 진행 중인 재구성 상태를 바꿀 수 있음).

## 환경변수 (`.env`)

| 이름 | 기본값 | 설명 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./easyclass.db` | DB 주소 |
| `STORAGE_DIR` | `./storage` | 페이지 PNG·생성 이미지 저장 위치 (`/files/...`로 제공) |
| `FRONTEND_ORIGINS` | `http://localhost:3000,http://localhost:5173` | CORS 허용 도메인 (쉼표 구분, Vercel 도메인 추가) |
| `JWT_SECRET` | — | **반드시 변경.** 32바이트 이상 랜덤 문자열 |
| `JWT_EXPIRE_MINUTES` | `720` | 로그인 토큰 유효 시간 |
| `MOCK_AI` | `true` | `true`면 텍스트 AI(재구성·자막·퀴즈·챗봇)를 호출하지 않고 고정 응답 |
| `MOCK_IMAGE` | `true` | `true`면 이미지 생성을 호출하지 않고 자리표시 이미지 (실제 호출은 1장 약 37크레딧) |
| `AI_BASE_URL` | `https://api.baze.co/v1/gateway` | Gateway 주소 |
| `AI_API_KEY` | — | Gateway 키. `.env`에만 두고 커밋·프론트 노출 금지 |
| `MODEL_FAST` / `MODEL_MAIN` / `MODEL_IMAGE` | `gemini-3.5-flash-lite` / `gemini-3.8-flash` / `gemini-nano-banana-2.1` | 실시간 자막 / 재구성·퀴즈·챗봇 / 이미지 |
| `IMAGE_SIZE`, `IMAGE_ASPECT_RATIO` | `1K`, `1:1` | 이미지 크기·비율 |
| `AI_TIMEOUT_SECONDS` | `90` | AI 호출 타임아웃 |
| `GENERATE_CONCURRENCY` | `3` | 페이지 재구성 동시 호출 수 |
| `LIVE_CAPTION_INTERVAL_SECONDS` | `15` | 같은 페이지 실시간 자막 호출 최소 간격 |
| `CHAT_HISTORY_LIMIT` | `10` | 챗봇이 문맥으로 쓰는 이전 대화 수 |
| `MAX_UPLOAD_MB`, `MAX_PDF_PAGES`, `PDF_RENDER_ZOOM` | `30`, `100`, `1.5` | PDF 업로드 제한·렌더링 배율 |

`MOCK_AI=false` 또는 `MOCK_IMAGE=false`인데 `AI_API_KEY`가 비어 있으면 서버가 시작하지 않습니다.
키를 넣은 뒤 연결 확인: `.venv/bin/python -m scripts.ai_smoke` (텍스트 1회), `--image` (이미지 1장 추가, 크레딧 소모)

## 시드 계정

`scripts/seed.py` 실행 후 (비밀번호 모두 `pass1234`)

| 역할 | 아이디 | 이름 |
|---|---|---|
| 교사 | `teacher1` | 김선생 |
| 학생 | `student1`, `student2`, `student3` | 이학생, 박학생, 최학생 |

과목 "과학"(초대 코드 `DEMO01`)이 만들어지고 학생 3명이 등록됩니다.

## 전체 흐름

```
교사: 과목 생성 ─ PDF 업로드 ─ 재구성(generate) ─ 검토·수정·이미지 ─ 승인 ─ 수업 시작 ─(WebSocket)─ 수업 종료 ─ 퀴즈 생성
학생: 초대 코드로 등록 ───────────────────────────────── 승인된 회차 열람 ─(WebSocket 자막)─ 퀴즈 풀이·챗봇
```

회차 상태: `uploaded → generating → ready → approved → live → ended` (ended → live로 재개 가능).
학생에게는 `approved` 이후 회차만 보이고, 그 전 회차는 404로 숨깁니다.

## API 요약

인증이 필요한 API는 `Authorization: Bearer <access_token>`. 에러는 `{"detail": "..."}`.
권한이 없으면 403, 없는 리소스는 404 (학생에게 승인 전 회차도 404). 자세한 요청/응답 스키마는 `/docs`.

| 메서드 | 경로 | 대상 | 설명 |
|---|---|---|---|
| POST | `/auth/signup` | 누구나 | `{login_id, password, name, role}` |
| POST | `/auth/login` | 누구나 | → `{access_token, user}` |
| GET | `/auth/me` | 로그인 | 내 정보 |
| POST | `/courses` | 교사 | 과목 생성 + 6자리 초대 코드 |
| GET | `/courses` | 둘 다 | 교사: 만든 과목 / 학생: 등록 과목 (학생에게 초대 코드는 `null`) |
| POST | `/courses/join` | 학생 | `{invite_code}` (대소문자 무시) |
| GET | `/courses/{id}` | 둘 다 | 과목 + 회차 목록 |
| GET | `/courses/{id}/students` | 교사 | 등록 학생 |
| POST | `/courses/{id}/lessons` | 교사 | multipart `file`(PDF), `session_no`, `title`, `class_date?` |
| POST | `/lessons/{id}/generate` | 교사 | 재구성 시작 (202, 진행률은 `GET /lessons/{id}`의 `progress`) |
| GET | `/lessons/{id}` | 둘 다 | 회차 + 페이지 (학생: 승인 내용만, 원문·이미지 제안 제외) |
| PUT | `/lessons/{id}/pages/{n}` | 교사 | `easy_sentences`, `hard_words` 수정 |
| POST / DELETE | `/lessons/{id}/pages/{n}/image` | 교사 | 이미지 생성(`{prompt?}`, 비우면 AI 제안 사용) / 삭제 |
| POST | `/lessons/{id}/approve` | 교사 | 승인 → 학생 공개 |
| POST | `/lessons/{id}/start`, `/end` | 교사 | 수업 시작·종료 (WebSocket으로 알림) |
| GET | `/lessons/{id}/pages/{n}` | 둘 다 | 학생 화면용 페이지 (쉬운 문장, 실시간 자막, `teacher_page`) |
| POST | `/lessons/{id}/quiz` | 교사 | 퀴즈 생성 (이미 있으면 200으로 기존 것, 생성에 10~25초) |
| GET | `/lessons/{id}/quiz` | 둘 다 | 학생에게는 정답·해설 제외 |
| POST | `/lessons/{id}/quiz/attempts` | 학생 | `{answers:[{question_id, answer}]}` → 채점 + 해설 |
| GET | `/lessons/{id}/quiz/attempts/me` | 학생 | 내 풀이 기록 (최신순) |
| POST | `/lessons/{id}/chat` | 학생 | `{message}` → `{question, answer}` (`answer.related_page`) |
| GET | `/lessons/{id}/chat` | 학생 | 내 대화 기록 |

정적 파일: `/files/pages/<uuid>.png`(원본 페이지), `/files/generated/<uuid>.(png|jpg)`(생성 이미지). 인증 없이 제공되며 파일명은 추측할 수 없는 UUID입니다.

## WebSocket

```
ws://localhost:8000/ws/lessons/{lesson_id}?token=<access_token>
```

- 교사는 과목 주인, 학생은 등록 학생만 접속할 수 있습니다. 역할은 토큰으로 판단합니다.
- 거부 시 연결 직후 아래 코드로 닫힙니다 (`CloseEvent.code`): `4401` 토큰 없음/무효, `4403` 권한 없음, `4404` 회차 없음(학생에게는 미승인 회차 포함)
- 접속(재접속) 즉시 현재 상태를 보냅니다: `teacher_page` → (자막이 있으면) 현재 페이지 `page_update` → (끝난 수업이면) `lesson_ended`
- 연결 유지: 20~30초마다 `{"type":"ping"}`을 보내면 `{"type":"pong"}`으로 답합니다.

교사 → 서버

```json
{"type": "page_change", "page_no": 2}
{"type": "transcript", "page_no": 2, "text": "이게 엽록체예요", "final": true}
{"type": "ping"}
```

- `transcript`는 Web Speech API의 확정 결과(`final: true`)만 보내세요. `final: false`는 저장하지 않고 `ignored`로 응답합니다.
- 수업이 `live`가 아니면 `error`로 응답합니다. 학생은 `ping`만 보낼 수 있습니다.

서버 → 교사·학생 모두 (broadcast)

```json
{"type": "teacher_page", "page_no": 2}
{"type": "page_update", "page_no": 1, "easy_transcript": ["식물은 스스로 양분을 만들어요.", "..."], "hard_words": [{"word": "광합성", "meaning": "..."}]}
{"type": "lesson_started", "page_no": 1}
{"type": "lesson_ended"}
```

- `page_update`의 `easy_transcript`는 그 페이지 자막 **전체**입니다 (덧붙이지 말고 교체). 이전 문장은 바뀌지 않고 뒤에 추가되는 형태입니다.
- 학생은 페이지를 자유롭게 이동하므로, 지금 보고 있는 페이지의 `page_update`만 화면에 반영하고 나머지는 페이지별로 보관하면 됩니다.
- `lesson_started`는 명세 외 추가 메시지입니다 (승인 회차에 미리 접속한 학생에게 시작을 알림).

서버 → 보낸 교사에게만

```json
{"type": "ack", "for": "transcript", "page_no": 2, "transcript_id": 15}
{"type": "ack", "for": "page_change", "page_no": 2}
{"type": "error", "detail": "수업이 진행 중이 아닙니다. ..."}
```

실시간 자막은 페이지의 첫 발화는 바로, 이후에는 마지막 호출 15초 뒤(새 발화가 있을 때), 페이지를 넘기거나 수업을 끝낼 때 갱신됩니다. 잡담·출석·생활지도 발화는 자막에서 빠집니다.

### 직접 시험하기

```bash
# 터미널 A: 학생 (받은 메시지 출력)
.venv/bin/python -m scripts.ws_client student1 2
# 터미널 B: 교사 (입력한 줄이 발화로 전송, /page N 페이지 이동, /ping, /quit)
.venv/bin/python -m scripts.ws_client teacher1 2
```

브라우저 콘솔:

```js
const ws = new WebSocket("ws://localhost:8000/ws/lessons/2?token=<토큰>");
ws.onmessage = (e) => console.log(JSON.parse(e.data));
ws.onclose = (e) => console.log("closed", e.code, e.reason);
```

## 데모 리플레이

미리 준비한 (시각, 페이지, 발화) JSON을 교사 클라이언트처럼 재생합니다. 마이크 없이 실시간 자막 시연이 가능합니다.

```bash
.venv/bin/python -m scripts.replay samples/replay_photosynthesis.json --lesson 2 --start --end
#   --speed 2 (배속)  --server URL  --teacher 아이디  --tail 초(마지막 자막 대기)
```

- `--start`: 재생 전 수업 시작 (승인된 회차여야 함), `--end`: 재생 후 수업 종료 (남은 발화도 자막 처리)
- 파일 형식은 `scripts/replay.py` 상단 설명 참고. `page_no`가 바뀌면 `page_change`를 자동으로 보냅니다.
- 학생 화면은 프론트 또는 `scripts.ws_client student1 2`로 확인하세요.
- `MOCK_AI=false`면 실제 자막 API가 호출됩니다 (빠른 모델, 재생 1회에 10회 안팎).

## AI 동작 메모

- 모든 출력은 "~해요"체, 짧은 문장. 원문에 없는 사실은 추가하지 않습니다 (챗봇의 기초 질문만 예외).
- 챗봇은 질문을 넷으로 나눕니다: 수업 내용 / 수업 주제와 이어지는 기초 질문(교과서 수준으로 답하고 근거 페이지 필수, 없으면 심화로 처리) / 심화("오늘 수업에서는 거기까지 나오지 않았어요…") / 무관("이건 오늘 수업과 다른 이야기예요…"). 걱정되는 말에는 어른에게 이야기하도록 안내합니다.
- 퀴즈는 OX·3지선다만, 부정형·함정 문제 없이 5문항 안팎. 3지선다 보기 순서는 서버에서 섞습니다.
- 프롬프트: `app/ai/prompts.py`, 출력 검증: `app/ai/schemas.py`, Gateway 호출: `app/ai/gateway.py`

## 프로젝트 구조

```
app/
  main.py            앱 생성, CORS, /files, /health, 시작 시 작업
  config.py db.py models.py schemas.py security.py deps.py permissions.py storage.py pdf.py
  routers/           auth, courses, lessons, quiz, chat, ws
  services/          generation(재구성), live(WebSocket·실시간 자막), quiz, chat, content
  ai/                provider 인터페이스, mock, gateway, prompts, schemas
scripts/             seed, ai_smoke, ws_client, replay
samples/             demo_lesson.pdf (3쪽 데모 자료), replay_photosynthesis.json
tests/               pytest (MOCK 모드)
```

## 해커톤 범위에서 하지 않은 것

이메일 인증·비밀번호 찾기·소셜 로그인, DB 마이그레이션 도구(필요한 컬럼만 시작 시 자동 추가), 여러 프로세스 확장,
교사용 반 전체 퀴즈 결과 API, 퀴즈 재생성(삭제) API, `/files` 인증.
