---
title: Archivum Terra
emoji: 🦅
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: cc-by-sa-3.0
short_description: Warhammer 40k 로어를 출처 인용과 함께 답하는 검색 아카이브
---

# Archivum Terra

Warhammer 40,000 로어를 자연어로 묻고 **출처 인용과 함께** 답을 받는 아카이브.

- 자료: [Warhammer 40k Wiki](https://warhammer40k.fandom.com) 본문 문서 7,299건 → 35,812청크 (CC BY-SA 3.0)
- 검색: BGE-M3 다국어 임베딩 + BM25 하이브리드 (한국어 질문 → 영어 문서 교차 검색)
- 답변: Puter 경유. 질문 언어를 따라가며, 근거에 없는 내용은 지어내지 않는다
- 방문자는 로그인 없이 바로 쓴다 (Puter 계정 자동 발급)

## 비밀이 없는 배포

이 Space 에는 **Secrets 가 하나도 없다.** 넣을 것이 없으므로 유출될 것도 없다.

| 보통 필요한 것 | 여기서는 |
|---|---|
| LLM API 키 | 없음 — 답변 생성은 브라우저가 Puter 로 직접 한다 |
| 인덱스 접근 토큰 | 없음 — 인덱스 Dataset repo 가 public 이라 익명으로 받는다 |
| OAuth 클라이언트 시크릿 | 없음 — Puter 계정을 그대로 쓴다 |

선택 설정(전부 생략 가능):

| 키 | 용도 |
|---|---|
| `HF_INDEX_REPO` | 인덱스 위치 (기본 `oiehnow/wh40k-lore-index`) |
| `PUTER_MODEL` | 사용할 모델 (기본 `gpt-5-nano`) |
| `GEMINI_API_KEY` | 넣으면 서버 생성 경로로 전환된다 |

---

Games Workshop과 무관한 비공식 팬 프로젝트입니다.
Warhammer 40,000은 Games Workshop Ltd.의 상표입니다.
