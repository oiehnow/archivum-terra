"""질의 임베딩 클라이언트.

인덱스는 BGE-M3(2.3GB)로 만들었다. 같은 모델로 질의를 벡터화해야 검색이 성립하는데,
무료 CPU 호스팅에 2.3GB 모델을 올릴 수 없다.

그래서 질의 임베딩만 HF Inference API 에 맡긴다. 서버에는 모델도 torch 도 없고
벡터 비교만 남아 메모리가 250MB 수준으로 내려간다.

로컬 개발처럼 모델을 직접 돌릴 수 있는 환경에서는 EMBED_BACKEND=local 로 전환한다.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request

from wh40k.embedding import query_text

HF_API = "https://router.huggingface.co/hf-inference/models/{model}/pipeline/feature-extraction"
BACKEND = os.getenv("EMBED_BACKEND", "api")  # "api" | "local"
TIMEOUT = int(os.getenv("EMBED_TIMEOUT", "30"))

_local_lock = threading.Lock()
_local_model = None


class EmbedError(RuntimeError):
    """질의를 벡터로 바꾸지 못했을 때."""


def _embed_via_api(question: str, model: str) -> list[float]:
    token = os.getenv("HF_TOKEN")
    if not token:
        raise EmbedError("HF_TOKEN 이 설정되지 않았습니다")

    payload = json.dumps({"inputs": query_text(question, model)}).encode()
    request = urllib.request.Request(
        HF_API.format(model=model),
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )

    last: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                vector = json.load(response)
        except urllib.error.HTTPError as exc:
            # 503 은 모델이 아직 올라오는 중이라는 뜻이라 잠시 뒤 다시 시도한다.
            if exc.code not in (429, 503) or attempt == 2:
                raise EmbedError(f"임베딩 API 오류 {exc.code}") from exc
            last = exc
            time.sleep(2 * (attempt + 1))
            continue
        except Exception as exc:
            last = exc
            if attempt == 2:
                raise EmbedError(f"임베딩 API 연결 실패: {exc}") from exc
            time.sleep(1)
            continue

        # 토큰 단위로 돌아오는 경우가 있어 문장 벡터 하나로 정규화한다.
        if vector and isinstance(vector[0], list):
            if vector[0] and isinstance(vector[0][0], list):
                vector = vector[0]
            dim = len(vector[0])
            vector = [sum(row[i] for row in vector) / len(vector) for i in range(dim)]
        return _normalize(vector)

    raise EmbedError(f"임베딩 실패: {last}")


def _normalize(vector: list[float]) -> list[float]:
    norm = sum(v * v for v in vector) ** 0.5
    return [v / norm for v in vector] if norm else vector


def _embed_local(question: str, model: str) -> list[float]:
    global _local_model
    if _local_model is None:
        with _local_lock:
            if _local_model is None:
                from sentence_transformers import SentenceTransformer

                _local_model = SentenceTransformer(
                    model, device="cpu", cache_folder=os.getenv("SENTENCE_TRANSFORMERS_HOME")
                )
    vector = _local_model.encode(query_text(question, model), normalize_embeddings=True)
    return vector.tolist()


def embed_query(question: str, model: str) -> list[float]:
    """질의를 인덱스와 같은 공간의 벡터로 만든다."""
    if BACKEND == "local":
        return _embed_local(question, model)
    return _embed_via_api(question, model)
