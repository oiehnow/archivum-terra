"""인덱스를 읽고 하이브리드 검색을 수행한다.

서비스 런타임은 GPU 가 없으므로 질의 임베딩도 CPU 로 돌린다.
BGE-M3 는 질의 하나 인코딩에 CPU 로도 100~300ms 수준이라 감당 가능하다.

인덱스는 HF Dataset repo 에서 내려받아 캐시한다 (Space 재시작 시 재사용).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from space.embed_client import embed_query
from wh40k.retrieve import drop_unmatched, merge_adjacent, reciprocal_rank_fusion

INDEX_DIR = Path(os.getenv("INDEX_DIR", "/data/index"))
INDEX_REPO = os.getenv("HF_INDEX_REPO", "oiehnow/wh40k-lore-index")
DEFAULT_EMBED_MODEL = "intfloat/multilingual-e5-small"

VECTOR_TOP_K = 30
BM25_TOP_K = 30
FUSED_TOP_N = 8

_lock = threading.Lock()
_state: dict = {}


def _download_index() -> Path:
    """인덱스가 없으면 HF Dataset repo 에서 내려받는다.

    repo 가 public 이라 토큰이 필요 없다. 덕분에 Space 에 저장할 비밀이 없다.
    """
    if (INDEX_DIR / "meta.json").exists():
        return INDEX_DIR

    from huggingface_hub import snapshot_download

    print(f"인덱스를 내려받는 중: {INDEX_REPO}")
    path = snapshot_download(
        repo_id=INDEX_REPO,
        repo_type="dataset",
        local_dir=str(INDEX_DIR),
    )
    return Path(path)


def _load() -> dict:
    """모델과 인덱스를 지연 로드한다 (콜드스타트를 첫 질문으로 미룬다)."""
    if _state:
        return _state

    with _lock:
        if _state:
            return _state

        import bm25s
        import lancedb

        index_dir = _download_index()
        meta = json.loads((index_dir / "meta.json").read_text(encoding="utf-8"))

        table = lancedb.connect(str(index_dir / "lance")).open_table("chunks")
        bm25 = bm25s.BM25.load(str(index_dir / "bm25"), load_corpus=False)

        # BM25 는 행 번호만 돌려주므로 청크 id 로 되돌릴 대응표가 필요하다.
        # 테이블 조회 순서에 의존하면 조용히 어긋날 수 있어 빌드 때 파일로 고정한다.
        ids = json.loads((index_dir / "bm25_ids.json").read_text(encoding="utf-8"))

        # 인덱스를 만든 모델과 반드시 같은 모델로 질의를 벡터화해야 한다.
        # 다르면 오류 없이 검색 결과만 무의미해지므로 meta 에 기록된 값을 따른다.
        embed_model = meta.get("embed_model", DEFAULT_EMBED_MODEL)

        _state.update(
            embed_model=embed_model,
            table=table,
            bm25=bm25,
            ids=ids,
            meta=meta,
        )
        print(f"인덱스 로드 완료: {meta['chunks']:,}청크 ({embed_model})")
    return _state


def search(question: str, top_n: int = FUSED_TOP_N) -> list[dict]:
    """벡터 검색과 BM25 를 합쳐 근거 청크를 고른다."""
    import bm25s

    state = _load()

    vector = embed_query(question, state["embed_model"])
    vector_hits = state["table"].search(vector).limit(VECTOR_TOP_K).to_list()
    vector_ranking = [hit["id"] for hit in vector_hits]

    tokens = bm25s.tokenize(question, stopwords="en", show_progress=False)
    bm25_ranking: list[str] = []
    try:
        rows, scores = state["bm25"].retrieve(tokens, k=BM25_TOP_K, show_progress=False)
        # 매칭이 없으면 bm25s 는 0점 문서를 순서대로 채워 돌려준다. 반드시 걸러낸다.
        bm25_ranking = drop_unmatched(
            [state["ids"][int(i)] for i in rows[0]],
            [float(s) for s in scores[0]],
        )
    except Exception:
        # 불용어만 남은 질의 등은 BM25 가 아무것도 못 찾는다. 벡터 검색만으로 진행한다.
        pass

    fused = reciprocal_rank_fusion([vector_ranking, bm25_ranking], top_n=top_n)
    if not fused:
        return []

    wanted = [doc_id for doc_id, _ in fused]
    quoted = ", ".join(f"'{i}'" for i in wanted)
    rows = state["table"].search().where(f"id IN ({quoted})").limit(len(wanted)).to_list()

    by_id = {row["id"]: row for row in rows}
    ordered = [by_id[i] for i in wanted if i in by_id]

    return merge_adjacent([
        {
            "title": row["title"],
            "section": row["section"],
            "text": row["text"],
            "source_url": row["source_url"] or None,
        }
        for row in ordered
    ])
