# Agent Guide: AI Shorts Generator

이 파일은 이 프로젝트를 처음 보는 AI/개발자가 `agent.md`만 읽고 수정, 기능 추가, 디버깅을 시작할 수 있도록 만든 작업 지침서입니다.

---

## 1. 프로젝트 한줄 요약

사용자가 웹 UI에서 주제와 방향을 입력하고 장면 수(8/10/12)를 선택하면,
호스트의 agy 워커로 쇼츠 대본/이미지를 생성하고 → Supertonic 로컬 TTS로 한국어 나레이션을 생성한 뒤 → Remotion/FFmpeg로 1080×1920 MP4를 렌더링하는 FastAPI 웹앱이다.

---

## 2. 기술 스택

| 영역 | 기술 |
|------|------|
| Backend | Python 3.9, FastAPI, Pydantic v2, Uvicorn |
| Frontend | 정적 HTML/CSS/Vanilla JS |
| Video Engine | Remotion v4, React 19, TypeScript, Node.js 20 |
| 대본/이미지 AI | **host-side agy workers** (`scripts/agy_text_worker.py`, `scripts/agy_image_worker.py`) |
| TTS | **Supertonic 로컬 ONNX TTS** (on-device, 한국어 전용) |
| Auth | JWT Bearer token, bcrypt |
| 배포 | Docker Compose, nginx 리버스 프록시 (포트 80→8000) |
| 스토리지 | 로컬 파일 시스템 (`output/`, `temp/`) |

> `prd.md`에는 Next.js/ElevenLabs 기반의 구버전 내용이 있다. 실제 구현은 위 스택이다.

---

## 3. 디렉토리 구조

```text
.
├── backend/
│   ├── main.py                    # FastAPI 앱, CORS, 라우터 등록, 정적 파일 서빙
│   ├── config.py                  # .env 로드, API 키/경로/영상 설정
│   ├── api/routes.py              # 모든 HTTP API + 비디오 생성 파이프라인 오케스트레이션
│   └── services/
│       ├── script_generator.py    # agy 텍스트 워커 → 대본/메타데이터 생성
│       ├── agy_text_client.py     # Docker↔호스트 agy 텍스트 요청 브리지
│       ├── image_generator.py     # agy 이미지 워커 요청 + 이미지 캐시
│       ├── narration_generator.py # TTS 호출, 볼륨 정규화, 속도 보정, Duration Guard
│       ├── supertonic_local_service.py  # Supertonic ONNX TTS 엔진 (싱글턴)
│       ├── google_tts_service.py  # Chirp3 voice 이름 매핑 (Supertonic style key로 변환)
│       ├── subtitle_generator.py  # SRT 자막 생성
│       ├── video_composer.py      # Remotion scene-data 생성, 렌더 실행, FFmpeg fallback
│       ├── youtube_uploader.py    # YouTube Data API 업로드
│       ├── history_store.py       # 생성 영상 보관함 (JSON 파일)
│       └── auth_service.py        # 로그인, JWT 발급/검증
├── frontend/
│   ├── index.html                 # 단일 페이지 UI
│   ├── app.js                     # 로그인, 대본 생성/수정, 에셋 업로드, polling, 보관함
│   └── style.css
├── video-engine/
│   ├── src/Root.tsx               # Remotion Composition 등록
│   ├── src/ShortsVideo.tsx        # 영상 레이아웃/자막/이미지/오디오 렌더링
│   ├── src/scene-data.json        # 렌더 직전 backend가 덮어쓰는 입력 JSON
│   └── package.json
├── systems/
│   ├── prompt_engine.md           # 대본 프롬프트 설계 원칙 (코드와 동기화 유지)
│   └── visual_style_dna.md        # 이미지 스타일 가이드
├── output/                        # 생성 결과, 업로드 이미지, 캐시, 보관함 (gitignore)
├── temp/                          # job별 임시 파일 (gitignore)
├── Dockerfile                     # Python + Node + Remotion + Supertonic 컨테이너
├── docker-compose.yml             # 프로덕션 서비스 정의 (볼륨 마운트 포함)
├── setup-linux.sh                 # Ubuntu/Debian 설치 스크립트
└── start_backend.sh               # 로컬 venv 기반 실행 스크립트
```

---

## 4. 환경변수

루트 `.env`를 `backend/config.py`와 `backend/services/auth_service.py`가 읽는다.

```env
# 대본/이미지는 Gemini API가 아니라 host-side agy worker를 사용한다.
# GOOGLE_GEMINI_API / GCP 관련 값은 있더라도 사용하지 않으며 필수도 아니다.
ELEVENLABS_API_KEY=...             # config 호환성용 필수 값
SUPER_TONE_API_KEY=...             # 현재 사용 안 함 (로컬 모델 사용)
IMAGE_PROVIDER=agy                 # auto/google 값도 agy로 매핑됨
AGY_TEXT_TIMEOUT=300
AGY_TEXT_REQUEST_TIMEOUT=360
AGY_IMAGE_TIMEOUT=180
AGY_IMAGE_REQUEST_TIMEOUT=240
MASTER_PASSWORD_HASH=$2b$12$...    # bcrypt 해시 (generate_password.py로 생성)
SECRET_KEY=...                     # JWT 서명 키
REMOTION_CODEC=h264
REMOTION_CONCURRENCY=4
REMOTION_CHROME_MODE=chrome-for-testing
REMOTION_BROWSER_EXECUTABLE=      # 비워두면 자동 감지
```

**Docker 주의**: `.env`의 bcrypt 해시에 `$` 기호가 있어 `docker compose up` 시 아래 경고가 나온다:

```
The "FCc4WJgm03..." variable is not set. Defaulting to a blank string.
```

이는 docker compose가 yml 파일의 변수 치환 시 `.env`를 읽다가 발생하는 **무해한 경고**다.
Python 앱은 `.env`를 볼륨 마운트로 직접 읽으므로 해시 값이 정상적으로 로드된다.

**절대 커밋/노출 금지 파일:**
`.env`, `google_cloud_key.json`, `gen-lang-client-*.json`, `token.pickle`, `client_secrets.json`

---

## 5. 실행 방법

### Docker (프로덕션)

```bash
# 최초 빌드 및 실행
docker compose up --build -d

# 코드 변경 후 재반영 (빌드 불필요 — 볼륨 마운트로 코드 공유됨)
docker compose restart shorts-app

# 로그 확인
docker compose logs -f shorts-app
```

**볼륨 마운트 설명** (docker-compose.yml):
- `./backend:/app/backend` — 백엔드 코드 변경 시 재시작만으로 반영
- `./frontend:/app/frontend` — 프론트엔드 변경 즉시 반영 (정적 파일)
- `./systems:/app/systems` — 프롬프트 문서 반영
- `./video-engine/src:/app/video-engine/src` — Remotion 소스 반영
- Python 패키지, npm 패키지, Supertonic ONNX 모델은 이미지에 포함 → 변경 시 `docker compose build` 필요

### 로컬 직접 실행

```bash
source .venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000
# 또는
./start_backend.sh
```

접속: `http://localhost:8000/` | 헬스체크: `GET /health` | API 문서: `/docs`

---

## 6. 핵심 데이터 흐름

```
로그인 (JWT 발급)
  ↓
POST /api/generate-script
  → agy_text_worker가 대본용 참고자료/대본 JSON 생성 (최대 2회 retry)
  → 발화량·제목 품질 검증 → agy_text_worker로 메타데이터 보강
  ↓
프론트에서 대본/장면/이미지 오버레이 편집
  ↓
POST /api/generate-video  (백그라운드 작업 시작)
  ↓ (background task)
  [Step 2] generate_scene_image() × N — agy_image_worker로 각 장면 이미지 생성 (캐시 활용)
  [Step 3] generate_all_narrations() — Supertonic 로컬 TTS → 볼륨 정규화 → Duration Guard
  [Step 4] compose_video() — scene-data.json 작성 → Remotion 렌더 → FFmpeg fallback
  ↓
output/shorts_{job_id}.mp4 저장
output/history/video_history.json에 보관함 기록
  ↓
GET /api/status/{job_id}  폴링으로 진행 상황 확인
```

---

## 7. 대본 생성 핵심 설계

### 장면 수별 발화량 계산

| 장면 수 | 목표 길이 | 발화량 범위 (공백 제외) | 장면당 |
|--------|---------|---------------------|------|
| 8장면  | 60초    | 286~350자 (목표 318자) | 32~48자 |
| 10장면 | 88초    | 419~513자 (목표 466자) | 37~56자 |
| 12장면 | 108초   | 515~629자 (목표 572자) | 38~57자 |

기준 TTS 속도: `KOREAN_NARRATION_CHARS_PER_SECOND = 5.3` (Supertonic 한국어 기준)

script_generator.py의 `SCENE_DURATION_TARGETS`와 narration_generator.py의 `SCENE_DURATION_TARGETS`는 **반드시 동기화 상태**를 유지해야 한다. 불일치 시 Duration Guard가 TTS 속도를 강제 조정해 부자연스러운 오디오가 된다.

### 바이럴 쇼츠 스토리 아크 (STAR_INSTRUCTOR_PROMPT)

프롬프트는 5단계 구조를 따른다:

1. **HOOK** (장면 1-2): 손해·반전·숫자로 첫 3초 안에 스크롤 정지
2. **TENSION BUILD** (장면 3-4): 공감대 + 긴장감 고조
3. **CORE FACTS** (중간): 한 장면 = 한 포인트, 구체적 수치/비교
4. **REVEAL** (뒷부분): 핵심 반전 공개
5. **OUTRO** (마지막): 1줄 요약 + 댓글 유도 CTA

### 제목 구조 (두 줄 카피)

- `video_title.highlight`: 공백 제외 **정확히 10자** (주제+상황+훅)
- `video_title.rest`: 공백 제외 **정확히 12자** (왜 봐야 하는지)
- 두 줄은 각자 독립된 카피. 한 문장 반토막 금지.

### 논리 일관성 체크 (중요)

프롬프트에 자기 검증 지시 포함. 흔한 실패 패턴:
- "X 마크만 보고 안심하면 안 됩니다" → "X 기능이 없을 수도 있습니다" → **모순** (마크가 있으면 기능도 있음)
- 드라마 효과를 위해 사실을 뒤집는 흐름 금지
- 올바른 접근: "X 마크가 있어도 특정 환경에서 호환성 문제가 있을 수 있습니다"

### 대본 생성 검증 로직

`generate_script()`는 다음 조건을 모두 만족해야 결과를 반환한다 (최대 2회 시도):

1. 장면 수 일치
2. 총 발화량이 `min_total_chars`~`max_total_chars` 범위 내
3. `video_title` 글자 수 정확히 일치 (10자/12자)
4. 제목 구조 검증 (`_video_title_structure_ok`)
5. 각 장면 스크립트 글자 수 + 문장 수(≤2) + 자연스러운 종결어미 확인

조건 미충족 시 retry 지시를 추가해 2차 시도.

---

## 8. TTS 파이프라인

### Supertonic 로컬 TTS

`supertonic_local_service.py` — 로컬 ONNX 모델 기반, 싱글턴 패턴

보이스 스타일 매핑:
```
ko-KR-Chirp3-HD-Achird → M1 (남성, 따뜻한 톤)
ko-KR-Chirp3-HD-Aoede  → F1 (여성, 차분한 톤)
... (6가지 스타일)
```

`google_tts_service.py`는 character role/gender → Chirp3 voice name 변환만 담당, 실제 합성은 Supertonic이 한다.

### 나레이션 생성 흐름 (`generate_all_narrations`)

1. 장면별 TTS 생성 (Supertonic)
2. **배치 정규화**: `loudnorm` + `atempo={base_speed_factor}` (기본값 1.0, 최대 1.08)
3. fade-in/out 30ms 적용
4. **Duration Guard**: 전체 오디오가 목표 범위를 벗어나면 추가 속도 조정

`base_speed_factor`는 스크립트 발화량이 많을 때만 최소한으로 올린다 (1.0→1.04→1.08). 이전에는 무조건 1.04 이상으로 올려 부자연스러웠으나 수정됨.

---

## 9. HTTP API

기본 prefix `/api`. 인증 필요 API는 `Authorization: Bearer <token>` 헤더 필요.

### `POST /api/login`

```json
요청: { "password": "..." }
응답: { "access_token": "jwt", "token_type": "bearer" }
```

`MASTER_PASSWORD_HASH`가 없으면 모든 비밀번호로 토큰 발급 (초기 설정용).

### `POST /api/generate-script`

```json
{
  "topic": "주제",
  "tags": ["태그"],
  "direction": "방향 또는 참고 자료 (150자 초과 시 research 단계 생략)",
  "style": "star-instructor",
  "scene_count": 12
}
```

`style`은 현재 `star-instructor`만 지원. `scene_count`는 8, 10, 12.

```json
응답: {
  "job_id": "8charid",
  "status": "script_ready",
  "script_data": { ... }
}
```

### `POST /api/generate-video`

```json
{ "script_data": { ... } }
```

즉시 `{ "job_id": "...", "status": "pending" }` 반환. 실제 작업은 백그라운드.

### `GET /api/status/{job_id}`

인증 불필요. status 값: `pending` / `generating_images` / `generating_narration` / `composing_video` / `completed` / `error` / `not_found`

### `POST /api/generate-image`

오버레이용 AI 이미지 생성. 캐시 (`output/cache/images/`) 활용.

```json
{ "prompt": "영어 이미지 설명", "scene_script": "장면 대사 문맥" }
```

### `POST /api/upload-asset`

`multipart/form-data`의 `file` 필드. `output/uploads/`에 저장. 응답: `{ "path": "uploads/uuid.png" }`.

이 경로를 `scene.overlays[].content` 또는 `script_data.full_audio_path`에 사용.

### `GET/POST /api/history/*`

보관함 CRUD. `GET /api/history/{id}`는 `script_data` 전체를 포함해 기존 영상 재편집에 활용 가능.

### `GET /api/download/{filename}`

`output/{filename}`을 attachment로 강제 다운로드 (모바일 호환).

### `POST /api/upload-youtube`

```json
{ "job_id": "...", "title": "...", "description": "...", "tags": ["..."] }
```

---

## 10. `script_data` 계약

영상 생성에서 가장 중요한 내부 데이터 구조:

```json
{
  "video_title": { "highlight": "공백제외10자", "rest": "공백제외12자" },
  "subject": "카테고리",
  "youtube_title": "유튜브 제목 #Shorts",
  "youtube_description": "설명 + 해시태그",
  "youtube_tags": ["태그"],
  "characters": [
    {
      "id": "narrator",
      "name": "내레이터",
      "description": "No visible presenter. Visual storytelling only.",
      "voice_category": "neutral",
      "age_group": "adult",
      "color": "#d4ff00"
    }
  ],
  "scenes": [
    {
      "scene_id": 1,
      "character_id": "narrator",
      "script": "나레이션 대사",
      "background_description": "English image prompt (no text)",
      "blackboard_content": "same as background_description",
      "duration": 8,
      "overlays": [
        { "type": "image", "content": "uploads/file.png", "position": "blackboard", "startTime": 0, "duration": 5 }
      ]
    }
  ],
  "duration_target": {
    "target_seconds": 108,
    "min_seconds": 98,
    "max_seconds": 116,
    "min_total_chars": 515,
    "max_total_chars": 629
  },
  "full_audio_path": "uploads/full-audio.mp3"
}
```

`full_audio_path`가 있으면 TTS를 생성하지 않고 전체 오디오 길이를 측정해 각 scene duration을 비율 재조정.

---

## 11. Remotion 입력 계약

`video_composer.py`가 `video-engine/src/scene-data.json`에 씀:

```json
{
  "videoTitle": { "highlight": "...", "rest": "..." },
  "subject": "...",
  "scenes": [
    {
      "sceneId": 1,
      "imagePath": "images/scene_1.png",
      "audioPath": "audio/narration_1.mp3",
      "script": "...",
      "durationInSeconds": 8.4,
      "overlays": []
    }
  ],
  "bgmPath": "bgm.mp3"
}
```

Public asset 위치: `video-engine/public/images/`, `audio/`, `uploads/`, `bgm.mp3`
렌더 완료 후 `_cleanup_public()`이 일부 파일을 정리함.

---

## 12. 프론트엔드 에러 처리

**`fetchWithAuth(url, options)`**: 모든 인증 API 호출에 사용. 아래 케이스를 처리:
- 네트워크 오류 → `throw new Error('서버 연결 실패...')`
- 401 → 토큰 삭제 + 로그인 오버레이 표시 + `throw new Error('인증이 만료되었습니다...')`

**`parseJson(res)`**: 모든 `response.json()` 대신 사용. Content-Type이 `application/json`이 아니면 (nginx 502 HTML 등) 명확한 오류 메시지로 변환:
```
서버 오류 (HTTP 502). 서버가 재시작 중이거나 일시적 오류입니다. 잠시 후 다시 시도해주세요.
```

**이전 버그**: `.json()` 직접 호출 시 서버 다운 상태의 nginx HTML 502 응답이 `Unexpected token '<', "<html>..."` 에러로 표시됐음. 수정 완료.

---

## 13. 개발/수정 원칙

- `script_generator.py`와 `narration_generator.py`의 `SCENE_DURATION_TARGETS`는 항상 동기화 유지.
- 새 API 추가 시 `routes.py`, `app.js`, 필요하면 `video_composer.py`, `ShortsVideo.tsx`까지 연결 확인.
- `scene_id`는 이미지/오디오 파일명과 연결되므로 중복 방지.
- `blackboard_content`와 `background_description`은 동일 내용. Remotion은 `background_description`을 씀.
- 이미지 프롬프트는 readable text 포함 금지 강력히 적용 중. 글자 표시 기능 추가 시 별도 오버레이 레이어로 처리.
- `jobs` dict는 in-memory. 서버 재시작 시 진행 중 job 상태 소실 (완료 영상/보관함은 파일로 유지).
- `cleanup_old_files()`는 12시간 이상 된 `temp/` 하위 job 디렉토리만 삭제. `output/`과 `output/uploads/`는 건드리지 않음.
- `video-engine/src/scene-data.json`은 렌더 때마다 덮어씀. 샘플 데이터는 별도 파일로 관리.

---

## 14. 검증 체크리스트

### 백엔드 문법 확인

```bash
source .venv/bin/activate
python -m py_compile backend/main.py backend/api/routes.py backend/services/*.py
```

### Docker에서 코드 변경 반영

```bash
# 코드만 변경 (패키지 변경 없음) → 재시작으로 충분
docker compose restart shorts-app

# 패키지 추가/Dockerfile 변경 → 이미지 재빌드 필요
docker compose up --build -d
```

### 전체 파이프라인 검증

1. `POST /api/login` → 토큰 발급
2. `POST /api/generate-script` → 대본 JSON 확인
3. 프론트 대본 미리보기 → 발화량 표시 확인
4. `POST /api/generate-video` → job_id 반환 확인
5. `GET /api/status/{job_id}` 폴링
6. `GET /output/shorts_{job_id}.mp4` 재생 확인
7. `GET /api/history` 보관함 저장 확인

---

## 15. 자주 발생하는 문제

| 증상 | 원인 | 해결 |
|------|------|------|
| `Unexpected token '<'` JSON 에러 | nginx가 HTML(502) 반환 (서버 재시작 중) | 잠시 후 재시도. `docker compose ps`로 컨테이너 상태 확인 |
| 앱 시작 실패 | `.env` 필수 키 누락 또는 `GOOGLE_APPLICATION_CREDENTIALS` 경로 오류 | `.env` 내용과 파일 경로 확인 |
| TTS 생성 실패 | Supertonic ONNX 모델 로드 실패 | `docker compose logs shorts-app`에서 Supertonic 초기화 오류 확인 |
| Remotion 렌더 실패 | Chrome for Testing 없음, xvfb 없음, `scene-data.json` 형식 오류 | 로그에서 실패 원인 확인. FFmpeg fallback으로 자동 재시도 |
| FFmpeg fallback 실패 | full audio 모드에서 scene별 audio path가 비어 있음 | `full_audio_path` 있는 경우 scene audio는 비어도 정상; FFmpeg fallback은 별도 보강 필요 |
| 서버 재시작 후 job 상태 없음 | in-memory jobs 초기화 | 정상 동작. 완료 영상은 `output/`, 기록은 `output/history/`에 있음 |
| 오버레이 이미지 렌더 누락 | overlay content 경로 불일치 또는 `video_composer.py`가 public에 복사 안 함 | overlay `content`가 `uploads/...` 형태인지, `output/uploads/`에 파일이 있는지 확인 |
| 대본이 너무 짧거나 길어 TTS 속도 조정됨 | `SCENE_DURATION_TARGETS` 불일치 (script_generator vs narration_generator) | 두 파일의 duration 목표값 동기화 확인 |
| 대본 논리 모순 ("마크 있는데 기능 없다" 등) | Gemini 할루시네이션 | 프롬프트의 논리 일관성 체크 규칙 강화. 재생성 후 내용 검토 |
| YouTube 업로드 실패 | OAuth `client_secrets.json`, `token.pickle` 없음 또는 scope 오류 | OAuth 파일과 권한 scope 확인 |

---

## 16. 파일별 빠른 수정 가이드

| 수정 목적 | 수정 파일 |
|----------|----------|
| 새 API 엔드포인트 추가 | `backend/api/routes.py` |
| 대본 프롬프트/바이럴 구조 개선 | `backend/services/script_generator.py` (STAR_INSTRUCTOR_PROMPT) |
| 장면 발화량/타이밍 조정 | `script_generator.py`의 `SCENE_DURATION_TARGETS` + `narration_generator.py`의 `SCENE_DURATION_TARGETS` (동시에) |
| TTS 속도/볼륨 보정 | `backend/services/narration_generator.py` |
| TTS 보이스 스타일 변경 | `backend/services/supertonic_local_service.py` (VOICE_STYLE_MAPPING) |
| 이미지 스타일/프롬프트 변경 | `backend/services/image_generator.py` (STYLE_DNA, build_structured_scene_prompt) |
| 영상 화면 구성/자막 변경 | `video-engine/src/ShortsVideo.tsx` |
| 새 환경변수/경로 추가 | `backend/config.py`, `.env` |
| 프론트 UI/인터랙션 변경 | `frontend/index.html`, `frontend/app.js`, `frontend/style.css` |
| 보관함 저장 구조 변경 | `backend/services/history_store.py` |
| 인증 방식 변경 | `backend/services/auth_service.py` |
| Docker 설정 변경 | `Dockerfile`, `docker-compose.yml` |
