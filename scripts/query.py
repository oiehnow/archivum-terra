"""검색 품질을 눈으로 확인하는 CLI.

웹 UI 를 붙이기 전에 여기서 검색이 제대로 되는지 먼저 본다.
검색 품질이 답변 품질의 상한이므로 이 단계를 통과하지 못하면 웹은 의미가 없다.

    python scripts/query.py "호루스 헤러시가 뭐야?"
    python scripts/query.py --smoke          # 한/영 대표 질문 일괄 점검
    python scripts/query.py "..." --answer   # Gemini 답변까지 생성
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("INDEX_DIR", str(ROOT / "data" / "index"))
os.environ.setdefault("QUOTA_DB", str(ROOT / "data" / "quota.sqlite3"))

SMOKE_QUESTIONS = [
    "호루스 헤러시가 뭐야?",
    "카디아는 왜 함락되었나?",
    "오크는 어떻게 번식해?",
    "황제는 지금 어떤 상태야?",
    "네크론이 잠에서 깬 이유는?",
    "Why did Cadia fall?",
    "Who is Abaddon the Despoiler?",
    "What is the Golden Throne?",
    "How do Space Marines get created?",
    "What happened during the Siege of Terra?",
]


def load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def show(question: str, verbose: bool = True) -> list[dict]:
    from space.search import search

    hits = search(question)
    print(f"\n\033[1m{question}\033[0m")
    if not hits:
        print("  검색 결과 없음")
        return []

    for i, hit in enumerate(hits, start=1):
        preview = hit["text"].split("\n", 1)[-1].replace("\n", " ")[:110]
        link = "링크없음" if not hit["source_url"] else ""
        print(f"  [{i}] {hit['title']} — {hit['section']} {link}")
        if verbose:
            print(f"      {preview}...")
    return hits


async def answer(question: str, hits: list[dict]) -> None:
    from space.llm import get_provider
    from wh40k.prompt import build_messages

    system, user = build_messages(question, hits)
    print("\n  \033[92m답변:\033[0m ", end="", flush=True)
    async for token in get_provider().stream(system, user):
        print(token, end="", flush=True)
    print()


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="?", help="질문")
    parser.add_argument("--smoke", action="store_true", help="대표 질문 일괄 점검")
    parser.add_argument("--answer", action="store_true", help="Gemini 답변까지 생성")
    args = parser.parse_args()

    if args.smoke:
        for question in SMOKE_QUESTIONS:
            show(question, verbose=False)
        return

    if not args.question:
        parser.error("질문을 입력하거나 --smoke 를 쓰세요")

    hits = show(args.question)
    if args.answer and hits:
        asyncio.run(answer(args.question, hits))


if __name__ == "__main__":
    main()
