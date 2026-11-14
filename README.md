# 토끼와 거북이 — 백엔드

경계선 지능(느린 학습자) 학생이 일반 학급 수업을 따라갈 수 있게 돕는 서비스의 백엔드입니다.
교사가 올린 수업 자료(PDF)를 AI가 쉬운 문장으로 바꾸고, 수업 중 교사의 말을 실시간 쉬운 자막으로 학생에게 보내며,
수업 후에는 확인 문제와 수업 범위 챗봇을 학생별로 제공합니다.

- 기술: Python 3.12+ (3.13에서 개발·테스트), FastAPI, SQLite + SQLModel, PyMuPDF, 안뇽GPT API Gateway
- 상세 명세: [CLAUDE.md](CLAUDE.md)
- **API 문서(프론트 연동 기준):** 서버 실행 후 http://localhost:8000/docs
  - 서버 없이 보려면 **[docs/openapi.json](docs/openapi.json)** (OpenAPI 3 명세). https://editor.swagger.io 에 붙여 넣거나 코드 생성기에 넣어 쓸 수 있습니다.
  - WebSocket은 OpenAPI에 포함되지 않으므로 아래 [WebSocket](#websocket) 절을 보세요.

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
- API 명세 파일 갱신: `.venv/bin/python -m scripts.export_openapi` → `docs/openapi.json`
  (라우터·스키마를 바꾸면 다시 실행해서 함께 커밋. 갱신을 빠뜨리면 테스트가 실패합니다)

> **서버는 프로세스 하나로만 실행하세요.** WebSocket 연결과 실시간 자막 상태를 메모리에 두기 때문에
> `--workers 2` 이상이나 여러 인스턴스로 띄우면 교사와 학생 메시지가 서로 전달되지 않습니다.
> 같은 DB에 서버를 두 개 띄우는 것도 피하세요 (시작 시 정리 작업이 서로의 진행 중인 재구성 상태를 바꿀 수 있음).

## 환경변수 (`.env`)

| 이름 | 기본값 | 설명 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./easyclass.db` | DB 주소 |
| `STORAGE_DIR` | `./storage` | 페이지 PNG·생성 이미지 저장 위치 (`/files/...`로 제공) |
| `FRONTEND_ORIGINS` | `http://localhost:3000,http://localhost:5173` | CORS 허용 도메인 (쉼표 구분, Vercel 도메인 추가). 같은 Wi-Fi 기기 접속은 아래 참고 |
| `JWT_SECRET` | — | **반드시 변경.** 32바이트 이상 랜덤 문자열 |
| `JWT_EXPIRE_MINUTES` | `720` | 로그인 토큰 유효 시간 |
| `MOCK_AI` | `true` | `true`면 텍스트 AI(재구성·자막·퀴즈·챗봇)를 호출하지 않고 고정 응답 |
| `MOCK_IMAGE` | `true` | `true`면 이미지 생성을 호출하지 않고 자리표시 이미지 (실제 호출은 1장 약 37크레딧) |
| `AI_BASE_URL` | `https://api.baze.co/v1/gateway` | Gateway 주소 |
| `AI_API_KEY` | — | Gateway 키. `.env`에만 두고 커밋·프론트 노출 금지 |
| `MODEL_MAIN` / `MODEL_IMAGE` | `gemini-3.8-flash` / `gemini-nano-banana-2.1` | 재구성·퀴즈·챗봇 / 이미지 |
| `MODEL_LIVE` | (비움 → `MODEL_MAIN`) | 실시간 자막. 자막이 나오기까지 보통 3~9초. `gemini-3.5-flash-lite`로 바꾸면 1~2초지만 용어 교정·설명 누락이 많아짐. (`MODEL_FAST`는 예전 설정이라 지금은 쓰지 않음) |
| `IMAGE_SIZE`, `IMAGE_ASPECT_RATIO` | `1K`, `1:1` | 이미지 크기·비율 |
| `AI_TIMEOUT_SECONDS` | `90` | AI 호출 타임아웃 |
| `GENERATE_CONCURRENCY` | `3` | 페이지 재구성 동시 호출 수 |
| `LIVE_CAPTION_INTERVAL_SECONDS` | `15` | 같은 페이지 실시간 자막 호출 최소 간격 |
| `CHAT_HISTORY_LIMIT` | `10` | 챗봇이 문맥으로 쓰는 이전 대화 수 |
| `MAX_UPLOAD_MB`, `MAX_PDF_PAGES`, `PDF_RENDER_ZOOM` | `30`, `100`, `1.5` | PDF 업로드 제한·렌더링 배율 |
| `SUPERSCHOOL_MOCK` | `true` | 슈퍼스쿨 연동을 가짜(정해진 계정·학사 일정)로 동작. 아래 "슈퍼스쿨 연동" 참고 |
| `SUPERSCHOOL_CLIENT_ID`, `SUPERSCHOOL_CLIENT_SECRET` | — | `SUPERSCHOOL_MOCK=false`일 때 필수. 슈퍼스쿨이 발급하는 앱 이름표·비밀번호. secret은 `.env`에만 |
| `SUPERSCHOOL_AUTHORIZE_URL`, `SUPERSCHOOL_TOKEN_URL`, `SUPERSCHOOL_API_BASE_URL`, `SUPERSCHOOL_SCOPE` | — | `SUPERSCHOOL_MOCK=false`일 때 슈퍼스쿨 OAuth·API 주소 |

### 같은 Wi-Fi의 다른 기기(태블릿·휴대폰)에서 접속하기

1. 서버 PC의 IP 확인: macOS `ipconfig getifaddr en0`, Windows `ipconfig` (예: `192.168.0.12`)
2. `.env`의 `FRONTEND_ORIGINS`에 프론트 주소를 추가하고 서버를 재시작
   ```
   FRONTEND_ORIGINS=http://localhost:3000,http://localhost:5173,http://192.168.0.12:5173
   ```
3. 서버를 모든 네트워크에서 받도록 실행 (기본 `127.0.0.1`은 같은 PC에서만 접속됨)
   ```bash
   .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
4. 프론트의 API·WebSocket 주소도 `http://192.168.0.12:8000`, `ws://192.168.0.12:8000`으로 맞추기.
   프론트 개발 서버도 외부 접속을 허용해야 합니다 (Vite: `npm run dev -- --host`).
   접속이 안 되면 PC 방화벽에서 8000·5173 포트를 허용하세요.

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

인증이 필요한 API는 `Authorization: Bearer <access_token>`. 자세한 요청/응답 스키마는 `/docs` 또는 [docs/openapi.json](docs/openapi.json).

**오류 형식**

- 대부분의 오류(400·401·403·404·409·413·502, 그리고 서버가 직접 판단한 일부 422)는 `detail`이 **문자열**입니다.
  ```json
  {"detail": "이미 사용 중인 아이디입니다"}
  ```
- 요청 본문·폼·경로 값이 스키마에 맞지 않는 **입력값 검증 오류(422)**는 `detail`이 **배열**입니다.
  ```json
  {"detail": [{"type": "string_too_short", "loc": ["body", "login_id"], "msg": "String should have at least 3 characters", "input": "ab", "ctx": {"min_length": 3}}]}
  ```
  `loc`의 마지막 값이 문제가 된 필드 이름입니다. 프론트에서는 `typeof detail === "string"`으로 두 경우를 나눠 처리하세요.
- 권한이 없으면 403, 없는 리소스는 404 (학생에게는 승인 전 회차도 404로 숨김), 로그인이 안 됐거나 토큰이 무효·만료면 401.

**입력 규칙**

- 아이디(`login_id`): 3~32자, 영문·숫자·`_` `.` `-`만 (한글 불가)
- 비밀번호: 4자 이상 (72바이트 이하)
- 초대 코드: 영문 대문자+숫자 6자 (예: `DEMO01`). 등록할 때는 소문자로 입력해도 됩니다.
- `class_date`: 날짜만 `YYYY-MM-DD` (예: `2026-11-20`). 시간을 붙이면 422.
- **회원가입은 토큰을 주지 않습니다.** `POST /auth/signup` 성공(201) 후 `POST /auth/login`으로 로그인해서 토큰을 받으세요.

| 메서드 | 경로 | 대상 | 설명 |
|---|---|---|---|
| POST | `/auth/signup` | 누구나 | `{login_id, password, name, role}` → 201 사용자 정보 (토큰 없음) |
| POST | `/auth/login` | 누구나 | `{login_id, password}` → `{access_token, token_type, user: {id, login_id, name, role, avatar_url}}` |
| GET | `/auth/me` | 로그인 | 내 정보 `{id, login_id, name, role, avatar_url, superschool_linked, school, created_at}` |
| GET | `/auth/superschool/start` | 누구나 | `?mode=login|link&redirect_uri&state&role?` → 슈퍼스쿨 화면으로 307 redirect (브라우저로 이동) |
| POST | `/auth/superschool/callback` | 누구나 | `{code, redirect_uri}` → `{access_token, token_type, user}` 슈퍼스쿨로 로그인 (처음이면 계정 생성) |
| POST / DELETE | `/auth/superschool/link` | 로그인 | `{code, redirect_uri}` → 내 정보 (슈퍼스쿨 연결) / 연결 해제 → 내 정보 |
| PATCH | `/auth/me` | 로그인 | 보낸 필드만 수정. `{name}` 이름 변경, `{avatar_url: null}` 프로필 사진 삭제 (아이디·역할은 못 바꿈) |
| POST | `/auth/me/avatar` | 로그인 | multipart `file` (JPEG/PNG/WebP, 2MB 이하) → `{avatar_url}`. 예전 사진은 지움 |
| POST | `/auth/me/password` | 로그인 | `{current, next}` → 204. 지금 비밀번호가 틀리면 400 `{"detail": "지금 비밀번호가 맞지 않아요"}` |
| POST | `/courses` | 교사 | `{name, description}` (`description` 생략 가능) → 과목 + 6자리 초대 코드 |
| GET | `/courses` | 둘 다 | 교사: 만든 과목 / 학생: 등록 과목. 항목마다 `lesson_count`(학생은 승인된 회차만 셈), 학생에게 `invite_code`는 `null` |
| POST | `/courses/join` | 학생 | `{invite_code}` (대소문자 무시) |
| GET | `/courses/{id}` | 둘 다 | 과목 + 회차 목록 |
| PATCH | `/courses/{id}` | 교사 | `{name?, description?}` 보낸 것만 수정 (초대 코드는 그대로) |
| GET | `/courses/{id}/students` | 교사 | 등록 학생 |
| POST | `/courses/{id}/lessons` | 교사 | multipart `file`(PDF), `session_no`, `title`, `class_date?`(`YYYY-MM-DD`) |
| PATCH | `/lessons/{id}` | 교사 | `{session_no?, title?, class_date?}` 회차 정보 수정. `class_date: null`이면 날짜 지움, 회차 번호가 겹치면 409. 수업 자료·페이지는 그대로 |
| POST | `/lessons/{id}/generate` | 교사 | 재구성 시작 (202, 진행률은 `GET /lessons/{id}`의 `progress`) |
| GET | `/lessons/{id}` | 둘 다 | 회차 + 페이지. 학생에게는 `source_text`(원문)와 `image_suggestion`(AI 이미지 제안)이 `null`, 원본 페이지 이미지 `image_url`은 그대로 내려감. 승인 안 된 페이지의 쉬운 문장·낱말·생성 이미지는 비어 있음 |
| PUT | `/lessons/{id}/pages/{n}` | 교사 | `easy_sentences`, `hard_words` 수정 |
| POST | `/lessons/{id}/pages/{n}/terms/explain` | 교사 | `{word}` → `{word, meaning}` 그 페이지 글을 문맥으로 낱말의 쉬운 뜻을 AI로 만듦 (저장 안 함, 확인 후 `PUT .../pages/{n}`의 `hard_words`로 저장). AI 실패 시 502 |
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
| GET | `/calendar?from=YYYY-MM-DD&to=YYYY-MM-DD` | 둘 다 | 기간 안(양 끝 포함)에 수업 날짜가 있는 회차 → `{superschool_linked, superschool_error, events: [{id, title, start, end, all_day, source: "lesson" | "superschool", category, lesson_id, lesson_status, course_name}]}`. 학생은 승인된 회차만. 슈퍼스쿨을 연결했으면 학사 일정도 함께. 수업 날짜에 시각이 없어 `all_day: true`. 최대 400일, ISO 날짜시간도 받음 |
| GET | `/lessons/{id}/annotations` | 둘 다 | 내 필기 전체 `{pages: [{page_no, strokes, updated_at}]}` (필기 있는 페이지만) |
| PUT | `/lessons/{id}/annotations/{n}` | 둘 다 | `{strokes}` → 그 페이지 내 필기를 통째로 덮어씀, 빈 배열이면 삭제 |

**필기 형식**: `strokes`는 `[{"tool": "pen" | "highlighter", "color": "#e5484d", "width": 0.004, "points": [[0.1, 0.2], [0.15, 0.22]]}]`. 좌표와 굵기는 페이지 너비·높이 기준 0~1 비율이라 화면 크기가 달라도 같은 자리에 그려집니다. 한 페이지 최대 1000획·점 5만 개. 필기는 교사·학생 모두 자기 것만 보입니다.

정적 파일: `/files/pages/<uuid>.png`(원본 페이지), `/files/generated/<uuid>.(png|jpg)`(생성 이미지), `/files/avatars/<uuid>.(jpg|png|webp)`(프로필 사진). 인증 없이 제공되며 파일명은 추측할 수 없는 UUID입니다.

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
{"type": "pointer", "page_no": 2, "x": 0.42, "y": 0.31}
{"type": "ping"}
```

- `transcript`는 Web Speech API의 확정 결과(`final: true`)만 보내세요. `final: false`는 저장하지 않고 `ignored`로 응답합니다.
- `transcript`의 `page_no`는 그 문장을 **말하기 시작할 때** 보던 페이지로 보내세요. 크롬은 말이 끊겨야 문장을 확정하므로, 확정된 순간의 페이지를 쓰면 말하면서 넘긴 경우 앞 페이지 설명이 다음 페이지로 들어갑니다 (프론트 `useSpeechRecognition`은 페이지를 넘기기 직전에 인식을 끊어 확정시킵니다).
- `pointer`는 레이저 포인터 위치(페이지 기준 0~1)입니다. `x`·`y`를 `null`로 보내면 숨김. 저장하지 않고 응답(ack)도 없으며 **학생에게만** 전달됩니다. 초당 20~25번 정도로 보내면 충분합니다.
- 수업이 `live`가 아니면 `error`로 응답합니다. 학생은 `ping`만 보낼 수 있습니다.

서버 → 교사·학생 모두 (broadcast)

```json
{"type": "teacher_page", "page_no": 2}
{"type": "page_update", "page_no": 3,
 "easy_transcript": [
   {"text": "지금부터 정리해요.", "type": "flow"},
   {"text": "식물은 빛으로 양분을 만들어요.", "type": "content"},
   {"text": "다음 시간까지 잎 하나를 가져와요.", "type": "notice"}
 ],
 "hard_words": [{"word": "광합성", "meaning": "..."}]}
{"type": "lesson_started", "page_no": 1}
{"type": "lesson_ended"}
```

- `page_update`의 `easy_transcript`는 그 페이지 자막 **전체**입니다 (덧붙이지 말고 교체). 이전 문장은 바뀌지 않고 뒤에 추가되는 형태입니다.
- 자막 항목 `type`: `content` 수업 내용 / `flow` 수업 흐름 안내("지금부터 정리해요", "이제 엽록체를 볼 거예요") / `notice` 과제·준비물 안내. 화면에서 `flow`는 구분선·작은 글씨, `notice`는 강조 상자처럼 다르게 보여 주면 좋습니다. `GET /lessons/{id}/pages/{n}`의 `easy_transcript`도 같은 형식입니다.
- 학생은 페이지를 자유롭게 이동하므로, 지금 보고 있는 페이지의 `page_update`만 화면에 반영하고 나머지는 페이지별로 보관하면 됩니다.
- `lesson_started`는 명세 외 추가 메시지입니다 (승인 회차에 미리 접속한 학생에게 시작을 알림).

서버 → 학생만

```json
{"type": "pointer", "page_no": 2, "x": 0.42, "y": 0.31}
{"type": "pointer", "page_no": 2, "x": null, "y": null}
```

- 선생님 레이저 포인터입니다. 학생이 같은 페이지를 보고 있을 때만 표시하세요. 선생님이 페이지를 넘기면(`teacher_page`) 지워 주세요.

서버 → 보낸 교사에게만

```json
{"type": "ack", "for": "transcript", "page_no": 2, "transcript_id": 15}
{"type": "ack", "for": "page_change", "page_no": 2}
{"type": "error", "detail": "수업이 진행 중이 아닙니다. ..."}
```

실시간 자막은 페이지의 첫 발화는 바로, 이후에는 마지막 호출 15초 뒤(새 발화가 있을 때), 페이지를 넘기거나 수업을 끝낼 때 갱신됩니다. 잡담·출석·생활지도 발화와 "다음 장 넘겨 볼까요", "여기 보세요" 같은 단순 이동 멘트는 자막에서 빠지고, 선생님이 아직 말하지 않은 페이지 내용은 자막에 넣지 않습니다.

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

## 슈퍼스쿨 연동 (OAuth 가정)

슈퍼스쿨은 외부 서비스용 API를 공개하지 않아서, **"API를 받았다면 이렇게 붙는다"**를 구현해 두고 지금은 가짜로 동작합니다.

| | `SUPERSCHOOL_MOCK=true` (기본) | `SUPERSCHOOL_MOCK=false` |
|---|---|---|
| 로그인·동의 화면 | 프론트의 개발용 화면 `/auth/superschool/mock` | 슈퍼스쿨 화면 (`SUPERSCHOOL_AUTHORIZE_URL`) |
| 계정 | `mock:student` → 학생 "지우", `mock:teacher` → 교사 "김하늘", `mock:link` → 지금 계정과 같은 사람 | 슈퍼스쿨 `/me` 응답 |
| 소속 | `천천중학교 2학년 3반` / `천천중학교 · 과학과` | `school_name` + 학년·반 또는 과목 |
| 학사 일정 | 오늘 기준 동아리·상담 주간·재량휴업일·체험학습·기말고사·축제 | 슈퍼스쿨 `/calendar` 응답 |

흐름 (OAuth 2.0 인가 코드 방식)

1. 프론트가 `state`를 만들어 보관하고 `GET /auth/superschool/start?mode=login|link&redirect_uri=…&state=…&role=?`로 이동
2. 백엔드가 슈퍼스쿨 로그인·동의 화면으로 redirect → 슈퍼스쿨이 `redirect_uri?code=…&state=…`로 돌려보냄
3. 프론트가 `state`가 같은지 확인하고 `code`를 백엔드로 보냄
   - 로그인: `POST /auth/superschool/callback {code, redirect_uri}` → `{access_token, user}` (처음이면 계정 생성)
   - 계정 연결: `POST /auth/superschool/link {code, redirect_uri}` (로그인 필요) → 내 정보
4. 백엔드가 `code`를 토큰으로 바꾸고(`client_secret` 사용) 사용자 정보·학사 일정을 받아 옴

- `redirect_uri`는 `FRONTEND_ORIGINS`에 있는 주소의 `/auth/superschool/callback`만 허용합니다 (code가 엉뚱한 곳으로 가지 않게).
- 슈퍼스쿨 토큰과 `client_secret`은 서버에만 두고 응답에 넣지 않습니다. 토큰이 만료되면 refresh_token으로 갱신합니다.
- 연결 해제: `DELETE /auth/superschool/link`. 슈퍼스쿨로 가입한 계정(비밀번호 없음)은 해제할 수 없습니다.
- 내 정보·로그인 응답의 `superschool_linked`, `school`, 그리고 `GET /calendar`의 학사 일정(`source: "superschool"`, `end`는 마지막 날 포함)으로 화면에 보여 줍니다. 학사 일정을 못 가져오면 수업 일정만 주고 `superschool_error`에 안내 문구를 넣습니다.
- **실제 API를 받으면** `.env`에 `SUPERSCHOOL_MOCK=false`와 client_id·secret·주소를 넣고, 응답 필드 이름이 다르면 `app/superschool/oauth.py`의 `_profile`·`_event` 변환만 고치면 됩니다. 가정한 요청·응답 형식은 그 파일 맨 위에 적혀 있습니다.

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
  routers/           auth, courses, lessons, quiz, chat, ws, annotations, calendar, superschool
  services/          generation(재구성), live(WebSocket·실시간 자막), quiz, chat, content, users
  ai/                provider 인터페이스, mock, gateway, prompts, schemas
  superschool/       슈퍼스쿨 연동 인터페이스, mock, oauth(실제 연동용)
scripts/             seed, ai_smoke, ws_client, replay
samples/             demo_lesson.pdf (3쪽 데모 자료), replay_photosynthesis.json
tests/               pytest (MOCK 모드)
```

## 해커톤 범위에서 하지 않은 것

이메일 인증·비밀번호 찾기, 실제 슈퍼스쿨 연동(구조만 구현, 지금은 mock), 슈퍼스쿨 토큰 암호화 저장, DB 마이그레이션 도구(필요한 컬럼만 시작 시 자동 추가), 여러 프로세스 확장,
교사용 반 전체 퀴즈 결과 API, 퀴즈 재생성(삭제) API, `/files` 인증.
