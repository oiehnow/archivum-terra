"""Fandom 위키와 HF 보조 데이터셋에서 원본을 수집한다.

네트워크 작업만 담당한다. 중단해도 이미 받은 문서는 건너뛰고 이어서 받는다.

    python scripts/collect.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wh40k.fandom import (  # noqa: E402
    MAX_PAGEIDS_PER_REQUEST,
    fetch_all_pages,
    fetch_pages_content,
    http_fetch,
)

DATA = Path(__file__).resolve().parent.parent / "data" / "raw"
FANDOM_JSONL = DATA / "fandom.jsonl"
HF_JSONL = DATA / "hf_lore.jsonl"

HF_DATASET = "vizn3r/warhammer40k-lore"


def collect_fandom() -> None:
    DATA.mkdir(parents=True, exist_ok=True)

    done: set[int] = set()
    if FANDOM_JSONL.exists():
        with FANDOM_JSONL.open(encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["pageid"])
                except (json.JSONDecodeError, KeyError):
                    continue
        print(f"이미 받은 문서 {len(done):,}건 — 건너뜁니다")

    print("문서 목록을 받는 중...")
    listing = fetch_all_pages(http_fetch)
    print(f"본문 문서 {len(listing):,}건")

    todo = [pid for pid, _ in listing if pid not in done]
    if not todo:
        print("새로 받을 문서가 없습니다")
        return

    batches = (len(todo) + MAX_PAGEIDS_PER_REQUEST - 1) // MAX_PAGEIDS_PER_REQUEST
    print(f"본문 {len(todo):,}건을 {batches}회에 나눠 받습니다\n")

    started = time.time()
    written = 0
    with FANDOM_JSONL.open("a", encoding="utf-8") as f:
        for page in fetch_pages_content(http_fetch, todo):
            f.write(json.dumps({
                "pageid": page.pageid,
                "title": page.title,
                "revid": page.revid,
                "url": page.url,
                "wikitext": page.wikitext,
            }, ensure_ascii=False) + "\n")
            written += 1
            if written % 250 == 0:
                elapsed = time.time() - started
                rate = written / elapsed
                remaining = (len(todo) - written) / rate if rate else 0
                print(f"  {written:>5,}/{len(todo):,}  ({rate:.0f}건/초, 남은 시간 {remaining/60:.1f}분)")

    print(f"\nFandom 수집 완료: {written:,}건 → {FANDOM_JSONL.name}")


def collect_hf() -> None:
    if HF_JSONL.exists():
        print(f"{HF_JSONL.name} 이미 존재 — 건너뜁니다")
        return

    print(f"\nHF 데이터셋 내려받는 중: {HF_DATASET}")
    from datasets import load_dataset

    dataset = load_dataset(HF_DATASET, split="train")
    with HF_JSONL.open("w", encoding="utf-8") as f:
        for row in dataset:
            f.write(json.dumps({"text": row["text"]}, ensure_ascii=False) + "\n")

    print(f"HF 수집 완료: {len(dataset):,}행 → {HF_JSONL.name}")


if __name__ == "__main__":
    collect_fandom()
    collect_hf()
