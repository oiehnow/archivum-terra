# Archivum Terra

Warhammer 40,000 로어를 자연어로 묻고 **출처 인용과 함께** 답을 받는 웹 아카이브.

**한국어로 물으면 영어 위키를 찾아 한국어로 답한다.** 방문자는 사이트에 들어오는 것 외에 할 일이 없다.

## 구조

```
[1회성]  내 PC ── 수집 → 청킹 → GPU 임베딩 ──> HF Dataset repo (public)
                                                      │
                                                      │ 이미지 빌드 때 굽는다
                                                      ▼
[상시]                                        Render 무료 (Docker, 226MB)
                                               ├ 검색만 수행
                                               └ 질의 임베딩은 HF Inference API
                                                      │
                                              브라우저가 Puter 로 답변 생성
```

내 PC는 **인덱스를 만들 때만** 쓴다. 서비스는 Render 에서 돌므로 PC 를 꺼도 동작한다.

| 층 | 선택 | 비용 |
|---|---|---|
| 자료 | Fandom 40k 위키 7,299문서 + `vizn3r/warhammer40k-lore` | 무료 (CC BY-SA 3.0) |
| 문서 임베딩 | BGE-M3 (다국어) · 로컬 GPU 1회성 | 무료 |
| 질의 임베딩 | HF Inference API (BGE-M3) | 무료 |
| 검색 | LanceDB 벡터 + BM25 → RRF 융합 | 무료 |
| 답변 | **Puter (User-Pays)** — 브라우저가 직접 호출 | **운영자 $0** |
| 호스팅 | Render 무료 (512MB) | 무료 |

### 왜 이런 구조인가

**답변 — 운영자 키 하나를 전원이 공유하면** 사람이 몰리는 순간 그날 몫이 동나 아무도 쓰지 못한다.
Puter 는 각 방문자가 자기 무료 할당량으로 쓰므로, 사용자가 몇 명이든 운영자 비용은 $0 이고 전체 상한도 없다.
서버는 LLM 키를 갖지 않는다.

**질의 임베딩 — 인덱스는 BGE-M3(2.3GB)로 만들었다.** 같은 모델로 질의를 벡터화해야 검색이 성립하는데
무료 호스팅에 2.3GB 를 올릴 수 없다. 경량 모델로 바꿔봤더니 12문항 중 Top-1 정확도가 8→6 으로 떨어지고
"황제는 지금 어떤 상태야?" 에 `Battle Barge` 가 1위로 나왔다. 그래서 **질의 임베딩만 HF Inference API 에
맡겨** 품질을 지키면서 서버에서 torch 를 걷어냈다 (2.3GB → 226MB).

**언어 — 원본이 전량 영어라 다국어 임베딩이 필수 요건이다.** 영어 전용 임베딩을 쓰면 한국어 질문에서
검색이 통째로 실패한다.

## 준비

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
cp .env.example .env
```

`.env` 에 필요한 것은 **하나뿐**이다.

| 키 | 발급처 | 용도 |
|---|---|---|
| `HF_TOKEN` | https://huggingface.co/settings/tokens (write) | 인덱스 업로드 + 질의 임베딩 API |

LLM 키도 OAuth 시크릿도 필요 없다.

## 인덱스 만들기

```bash
python scripts/collect.py       # Fandom + HF 수집 (중단해도 이어받음)
python scripts/build_index.py   # 정규화 → 청킹 → 임베딩 → 인덱스   (GPU 권장)
python scripts/publish_index.py # HF Dataset repo 에 public 으로 업로드
```

## 로컬 실행

```bash
uv pip install -e ".[space]"
HF_TOKEN=... EMBED_BACKEND=api INDEX_DIR=data/index QUOTA_DB=data/quota.sqlite3 \
  AUTH_DISABLED=1 uvicorn space.app:app --reload
```

검색 품질만 빠르게 보려면:

```bash
python scripts/query.py --smoke          # 한/영 12문항 일괄 점검
python scripts/query.py "카디아는 왜 함락되었나?"
```

## 배포 (Render)

1. https://render.com 에서 GitHub 로 로그인하고 이 저장소를 연결한다
2. **New + → Blueprint** 로 `render.yaml` 을 읽힌다
3. `HF_TOKEN` 만 대시보드에서 직접 입력한다 (`sync: false` 라 저장소에 들어가지 않는다)

인덱스는 이미지 빌드 때 구워 넣는다. 무료 플랜은 유휴 시 컨테이너를 재우는데, 매번 200MB 를
내려받으면 첫 방문자가 오래 기다리기 때문이다.

## 테스트

```bash
pytest
```

순수 로직(정규화·청킹·파싱·검색 융합·프롬프트·임베딩 설정)은 네트워크와 GPU 없이 전부 검증된다.

## 라이선스와 고지

자료는 [Warhammer 40k Wiki](https://warhammer40k.fandom.com) 에서 왔으며
[CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) 을 따른다.
Games Workshop 과 무관한 **비공식 팬 프로젝트**이며, Warhammer 40,000 은 Games Workshop Ltd. 의 상표다.
