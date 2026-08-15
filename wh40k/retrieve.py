"""하이브리드 검색 결과 융합.

벡터 검색은 의미가 가까운 문서를, BM25 는 고유명사가 정확히 일치하는 문서를 찾는다.
40k 로어는 고유명사(Cadia, Horus, Krieg)가 질문의 핵심이라 어느 한쪽만으로는 부족하다.

두 검색기의 점수 단위가 달라 직접 더할 수 없으므로 순위만 쓰는 RRF 로 합친다.
리랭커는 두지 않는다 — Gemini 의 컨텍스트가 충분히 커서 상위 청크를 그대로 넘기면 된다.
"""

from __future__ import annotations

from collections.abc import Sequence

DEFAULT_K = 60
DEFAULT_TOP_N = 8


def drop_unmatched(
    doc_ids: Sequence[str], scores: Sequence[float], min_score: float = 1e-9
) -> list[str]:
    """매칭되지 않은 BM25 결과를 버린다.

    bm25s 는 겹치는 토큰이 하나도 없어도 문서를 앞에서부터 채워 돌려준다.
    한국어 질의는 영어 인덱스와 토큰이 겹치지 않아 전부 0점이 나오는데,
    이를 그대로 RRF 에 넣으면 인덱스 앞쪽 문서들이 검색 결과를 오염시킨다.
    """
    return [
        doc_id
        for doc_id, score in zip(doc_ids, scores)
        if score > min_score
    ]


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]],
    k: int = DEFAULT_K,
    top_n: int = DEFAULT_TOP_N,
) -> list[tuple[str, float]]:
    """여러 검색 결과를 순위 기반으로 합친다.

    각 문서 점수는 sum(1 / (k + 순위)). k 가 작을수록 1위의 우위가 커진다.
    양쪽 검색기에 모두 잡힌 문서가 한쪽에서만 1위인 문서보다 위로 올라온다.
    """
    scores: dict[str, float] = {}

    for ranking in rankings:
        seen: set[str] = set()
        for rank, doc_id in enumerate(ranking, start=1):
            if doc_id in seen:
                continue  # 같은 목록 안의 중복이 점수를 부풀리지 않게 한다
            seen.add(doc_id)
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)

    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return ordered[:top_n]


def merge_adjacent(hits: list[dict]) -> list[dict]:
    """같은 문서에서 온 여러 섹션을 하나로 합친다.

    한 문서의 여러 섹션이 따로 인용되면 같은 출처 링크가 반복 노출된다.
    본문을 이어 붙여 문맥을 살리고 인용은 한 건으로 만든다.
    """
    merged: dict[str, dict] = {}
    order: list[str] = []

    for hit in hits:
        title = hit["title"]
        if title not in merged:
            merged[title] = {**hit, "section": hit["section"], "text": hit["text"]}
            order.append(title)
            continue

        entry = merged[title]
        entry["section"] = f"{entry['section']}; {hit['section']}"
        entry["text"] = f"{entry['text']}\n\n{hit['text']}"

    return [merged[title] for title in order]
