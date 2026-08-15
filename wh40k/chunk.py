"""문서를 검색 단위로 쪼개고 중복을 제거한다.

토크나이저를 로컬 의존성으로 두지 않기 위해 길이는 문자 수로 근사한다.
BGE-M3 는 8192 토큰까지 받지만, 검색 정밀도를 위해 청크는 훨씬 작게 유지한다.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

# 문자 기준 기본값 (영문 대략 4자 ≈ 1토큰 → 3000자 ≈ 750토큰)
DEFAULT_MAX_CHARS = 3000
DEFAULT_OVERLAP = 400
DEFAULT_MIN_CHARS = 80

_RE_PARA = re.compile(r"\n\s*\n")
_RE_TITLE_KEY = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class Chunk:
    id: str
    title: str
    section: str
    text: str
    source_url: str | None
    source: str  # "fandom" | "hf"


def _chunk_id(title: str, section: str, index: int, text: str) -> str:
    digest = hashlib.sha1(f"{title}|{section}|{index}|{text}".encode()).hexdigest()
    return digest[:16]


def _split_body(body: str, max_chars: int, overlap: int) -> list[str]:
    """문단 경계를 지키며 본문을 나눈다. 단어 중간에서 자르지 않는다."""
    if len(body) <= max_chars:
        return [body]

    paragraphs = [p.strip() for p in _RE_PARA.split(body) if p.strip()]
    pieces: list[str] = []
    current = ""

    for para in paragraphs:
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= max_chars or not current:
            current = candidate
            continue
        pieces.append(current)
        # 직전 조각의 꼬리를 겹쳐 문맥이 끊기지 않게 한다.
        tail = current[-overlap:] if overlap else ""
        if tail:
            tail = tail[tail.find(" ") + 1 :] if " " in tail else tail
            current = f"{tail}\n\n{para}"
        else:
            current = para

    if current:
        pieces.append(current)
    return pieces


def chunk_document(
    title: str,
    sections: list[tuple[str, str]],
    source_url: str | None,
    source: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
    min_chars: int = DEFAULT_MIN_CHARS,
) -> list[Chunk]:
    """(섹션명, 본문) 목록을 검색 가능한 청크로 만든다.

    각 청크 앞에 "문서명 — 섹션명" 을 붙인다. 섹션 본문만으로는
    어느 문서의 내용인지 알 수 없어 검색 정확도가 떨어지기 때문이다.
    """
    chunks: list[Chunk] = []

    for section, body in sections:
        body = body.strip()
        if len(body) < min_chars:
            continue

        for index, piece in enumerate(_split_body(body, max_chars, overlap)):
            text = f"{title} — {section}\n{piece}"
            chunks.append(
                Chunk(
                    id=_chunk_id(title, section, index, piece),
                    title=title,
                    section=section,
                    text=text,
                    source_url=source_url,
                    source=source,
                )
            )
    return chunks


def _dedupe_key(chunk: Chunk) -> tuple[str, str]:
    norm = lambda s: _RE_TITLE_KEY.sub(" ", s.lower()).strip()  # noqa: E731
    return norm(chunk.title), norm(chunk.section)


def dedupe(chunks: list[Chunk]) -> list[Chunk]:
    """같은 문서·섹션이 여러 출처에서 온 경우 하나만 남긴다.

    Fandom 쪽을 우선한다. 최신이고 출처 URL 을 가지고 있어 인용 링크를 걸 수 있다.
    입력 순서는 유지한다.
    """
    best: dict[tuple[str, str], int] = {}
    kept: list[Chunk | None] = []

    for chunk in chunks:
        key = _dedupe_key(chunk)
        if key not in best:
            best[key] = len(kept)
            kept.append(chunk)
            continue

        position = best[key]
        incumbent = kept[position]
        assert incumbent is not None
        if incumbent.source != "fandom" and chunk.source == "fandom":
            kept[position] = chunk

    return [c for c in kept if c is not None]
