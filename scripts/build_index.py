"""수집한 원본을 검색 인덱스로 만든다.

정규화 → 청킹 → 중복 제거 → BGE-M3 임베딩 → LanceDB + BM25.

임베딩은 로컬 GPU 를 쓴다 (RTX 5080 기준 5만여 청크에 4분 내외).
서비스 런타임은 이 인덱스 파일만 읽으므로 GPU 가 필요 없다.

    python scripts/build_index.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wh40k.chunk import Chunk, chunk_document, dedupe  # noqa: E402
from wh40k.embedding import doc_text, get_config  # noqa: E402
from wh40k.hf_source import build_title_index, group_rows, resolve_url_indexed  # noqa: E402
from wh40k.normalize import split_sections  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

# 서비스는 무료 CPU 호스팅에서 돌아야 하므로 가벼운 모델을 기본으로 쓴다.
EMBED_MODEL = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-small")
INDEX = Path(os.getenv("INDEX_OUT", str(ROOT / "data" / "index")))
EMBED_BATCH = 64


def load_fandom_chunks() -> tuple[list[Chunk], dict[str, str]]:
    path = RAW / "fandom.jsonl"
    if not path.exists():
        raise SystemExit(f"{path} 가 없습니다. 먼저 scripts/collect.py 를 실행하세요.")

    chunks: list[Chunk] = []
    urls: dict[str, str] = {}

    with path.open(encoding="utf-8") as f:
        for line in f:
            doc = json.loads(line)
            urls[doc["title"]] = doc["url"]
            sections = split_sections(doc["wikitext"])
            chunks.extend(chunk_document(doc["title"], sections, doc["url"], "fandom"))

    print(f"Fandom  : 문서 {len(urls):,}건 → 청크 {len(chunks):,}개")
    return chunks, urls


def load_hf_chunks(fandom_urls: dict[str, str]) -> list[Chunk]:
    path = RAW / "hf_lore.jsonl"
    if not path.exists():
        print("HF      : 파일 없음 — 건너뜁니다")
        return []

    with path.open(encoding="utf-8") as f:
        rows = [json.loads(line)["text"] for line in f]

    title_index = build_title_index(fandom_urls)
    chunks: list[Chunk] = []
    linked = 0

    for title, sections in group_rows(rows).items():
        url = resolve_url_indexed(title, title_index)
        linked += url is not None
        chunks.extend(chunk_document(title, sections, url, "hf"))

    print(f"HF      : 행 {len(rows):,}개 → 청크 {len(chunks):,}개 (URL 매칭 {linked:,}문서)")
    return chunks


def embed(texts: list[str]):
    import torch
    from sentence_transformers import SentenceTransformer

    if not torch.cuda.is_available():
        raise SystemExit("CUDA 를 쓸 수 없습니다. GPU 없이 5만 청크 임베딩은 비현실적입니다.")

    print(f"\n임베딩 모델 로드: {EMBED_MODEL} ({torch.cuda.get_device_name(0)})")
    model = SentenceTransformer(
        EMBED_MODEL, device="cuda", model_kwargs={"torch_dtype": torch.float16}
    )

    started = time.time()
    # 모델이 요구하는 문서 접두어를 붙인다 (e5 계열은 "passage: ")
    vectors = model.encode(
        [doc_text(t, EMBED_MODEL) for t in texts],
        batch_size=EMBED_BATCH,
        show_progress_bar=True,
        normalize_embeddings=True,
    )
    print(f"임베딩 완료: {len(texts):,}개 / {time.time()-started:.0f}초")
    return vectors


def build(chunks: list[Chunk]) -> None:
    import bm25s
    import lancedb
    import pyarrow as pa

    if INDEX.exists():
        shutil.rmtree(INDEX)
    INDEX.mkdir(parents=True)

    vectors = embed([c.text for c in chunks])

    print("\nLanceDB 테이블 생성 중...")
    schema = pa.schema([
        pa.field("id", pa.string()),
        pa.field("title", pa.string()),
        pa.field("section", pa.string()),
        pa.field("text", pa.string()),
        pa.field("source_url", pa.string()),
        pa.field("source", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), vectors.shape[1])),
    ])
    rows = [
        {
            "id": c.id,
            "title": c.title,
            "section": c.section,
            "text": c.text,
            "source_url": c.source_url or "",
            "source": c.source,
            "vector": vectors[i].tolist(),
        }
        for i, c in enumerate(chunks)
    ]
    db = lancedb.connect(str(INDEX / "lance"))
    db.create_table("chunks", data=rows, schema=schema)

    print("BM25 인덱스 생성 중...")
    tokens = bm25s.tokenize([c.text for c in chunks], stopwords="en", show_progress=False)
    retriever = bm25s.BM25()
    retriever.index(tokens, show_progress=False)
    retriever.save(str(INDEX / "bm25"))

    # BM25 는 행 번호만 돌려주므로 청크 id 로 되돌릴 대응표를 함께 저장한다.
    # 테이블 조회 순서에 의존하면 조용히 어긋날 수 있다.
    (INDEX / "bm25_ids.json").write_text(
        json.dumps([c.id for c in chunks]), encoding="utf-8"
    )

    (INDEX / "meta.json").write_text(
        json.dumps(
            {
                "chunks": len(chunks),
                "dim": int(vectors.shape[1]),
                "embed_model": EMBED_MODEL,
                "license": "CC BY-SA 3.0",
                "sources": ["warhammer40k.fandom.com", "vizn3r/warhammer40k-lore"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n인덱스 저장 완료 → {INDEX}")


if __name__ == "__main__":
    fandom_chunks, fandom_urls = load_fandom_chunks()
    hf_chunks = load_hf_chunks(fandom_urls)

    merged = dedupe(fandom_chunks + hf_chunks)
    dropped = len(fandom_chunks) + len(hf_chunks) - len(merged)
    print(f"중복 제거: {dropped:,}개 제거 → 최종 {len(merged):,}청크")

    build(merged)
