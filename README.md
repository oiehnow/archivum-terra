# Archivum Terra

Warhammer 40,000 로어를 자연어로 묻고 **출처 인용과 함께** 답을 받는 웹 서비스.

방문자는 간편 로그인만 하면 바로 쓴다. API 키 발급 같은 준비는 필요 없다.

## 구조

```
[1회성] 내 PC ── 수집 → 청킹 → GPU 임베딩 → 인덱스 ── 업로드 ──┐
                                                              ▼
                                            HF Dataset repo (인덱스 보관)
                                                              │ 시작 시 내려받음
[상시]                                              HF Spaces (무료 CPU)
                                                     FastAPI + Gemini Flash
```

내 PC는 **인덱스를 만들 때만** 쓴다. 서비스는 HF Spaces에서 도므로 PC를 꺼도 계속 동작한다.

| 층 | 선택 | 비용 |
|---|---|---|
| 자료 | Fandom 40k 위키 7,299문서 + `vizn3r/warhammer40k-lore` | 무료 (CC BY-SA 3.0) |
| 임베딩 | BGE-M3 (다국어) · 로컬 RTX 5080 | 무료 |
| 검색 | LanceDB 벡터 + BM25 → RRF 융합 | 무료 |
| **추론** | **Puter (User-Pays)** — 브라우저가 직접 호출 | **운영자 $0** |
| 로그인 | Puter 계정 (방문 시 자동 발급) | 무료 |
| 호스팅 | HF Spaces 무료 CPU | 무료 |

### 왜 Puter인가

운영자 키 하나를 전원이 공유하면 사람이 늘수록 1인분이 줄어든다. Puter는 **각 방문자가 자기 할당량**을
쓰므로 사용자가 몇 명이든 운영자 비용은 $0이고 전체 상한도 없다. 서버는 LLM 키를 갖지 않는다.

서버는 검색만 하고(`POST /api/retrieve`) 근거와 프롬프트를 돌려준다. 답변 생성은 브라우저가
`puter.ai.chat()`으로 직접 한다.

운영자가 `GEMINI_API_KEY`를 넣으면 서버 생성 경로(`POST /api/ask`, 계정당 하루 20질문)로 자동 전환된다.
`llm.py`의 `LLMProvider` 프로토콜만 구현하면 다른 모델로도 갈아끼울 수 있다.

### 왜 다국어 임베딩인가

원본 자료는 전량 영어인데 답변은 질문 언어를 따라가야 한다. 영어 전용 임베딩을 쓰면
한국어 질문에서 검색이 통째로 실패하므로 BGE-M3로 고정했다.

## 준비

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
cp .env.example .env    # 값 채우기
```

`.env`에 필요한 것은 **하나뿐**이다:

| 키 | 발급처 | 필수 |
|---|---|---|
| `HF_TOKEN` | https://huggingface.co/settings/tokens (write 권한) | 인덱스 업로드용 |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey | 선택 (서버 생성 경로) |
| `GOOGLE_CLIENT_ID` / `SECRET` | https://console.cloud.google.com/apis/credentials | 선택 (서버 경로 로그인) |

Puter 경로로 운영하면 LLM 키도 OAuth 설정도 필요 없다. 방문자는 사이트에 들어오는 것 외에 할 일이 없다.

## 인덱스 만들기

```bash
python scripts/collect.py       # Fandom + HF 수집 (중단해도 이어받음)
python scripts/build_index.py   # 정규화 → 청킹 → 임베딩 → 인덱스  (GPU 필요)
python scripts/publish_index.py # HF Dataset repo 업로드
```

## 로컬 실행

```bash
uv pip install -e ".[space]"
AUTH_DISABLED=1 INDEX_DIR=data/index QUOTA_DB=data/quota.sqlite3 \
  uvicorn space.app:app --reload
```

## 배포

`space/` 를 HF Space(Docker SDK)에 푸시하고, Space Secrets에
`GEMINI_API_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SESSION_SECRET`,
`HF_TOKEN`, `OAUTH_REDIRECT_URI` 를 등록한다.

## 테스트

```bash
pytest
```

순수 로직(정규화·청킹·파싱·검색 융합·프롬프트)은 네트워크와 GPU 없이 전부 검증된다.

## 라이선스와 고지

자료는 [Warhammer 40k Wiki](https://warhammer40k.fandom.com)에서 왔으며
[CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/)을 따른다.
Games Workshop과 무관한 **비공식 팬 프로젝트**이며, Warhammer 40,000은 Games Workshop Ltd.의 상표다.
