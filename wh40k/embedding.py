"""임베딩 모델 설정.

인덱스를 만들 때와 검색할 때가 반드시 같은 모델·같은 접두어 규칙을 써야 한다.
어긋나면 오류 없이 검색 품질만 조용히 무너지므로 설정을 한 곳에 모은다.

e5 계열은 비대칭 검색용으로 학습되어 질의에 "query: ", 문서에 "passage: " 를 붙인다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EmbedConfig:
    dim: int
    query_prefix: str = ""
    doc_prefix: str = ""


EMBED_MODELS: dict[str, EmbedConfig] = {
    # 서비스 기본: 가벼워서 무료 CPU 호스팅에 올라간다
    "intfloat/multilingual-e5-small": EmbedConfig(
        dim=384, query_prefix="query: ", doc_prefix="passage: "
    ),
    "intfloat/multilingual-e5-base": EmbedConfig(
        dim=768, query_prefix="query: ", doc_prefix="passage: "
    ),
    # 품질은 가장 좋지만 2GB 를 써서 무료 호스팅에 올라가지 않는다
    "BAAI/bge-m3": EmbedConfig(dim=1024),
}


def get_config(model: str) -> EmbedConfig:
    """등록된 모델 설정을 돌려준다. 모르는 모델은 거부한다.

    접두어 규칙을 모르는 채로 쓰면 검색이 조용히 나빠지므로 기본값을 두지 않는다.
    """
    if model not in EMBED_MODELS:
        raise KeyError(
            f"등록되지 않은 임베딩 모델: {model}. "
            f"wh40k/embedding.py 의 EMBED_MODELS 에 접두어 규칙과 함께 추가하세요."
        )
    return EMBED_MODELS[model]


def query_text(question: str, model: str) -> str:
    """질의에 모델이 요구하는 접두어를 붙인다."""
    return get_config(model).query_prefix + question


def doc_text(text: str, model: str) -> str:
    """문서에 모델이 요구하는 접두어를 붙인다."""
    return get_config(model).doc_prefix + text
