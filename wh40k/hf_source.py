"""보조 데이터셋 vizn3r/warhammer40k-lore 파서.

각 행은 "{제목} - {섹션}: {본문}" 한 줄이다. Fandom 위키를 스크랩한 것이지만
출처 URL 이 없어, 인용 링크를 걸려면 Fandom 문서 제목과 맞춰 URL 을 역으로 채워야 한다.

같은 섹션이 여러 행으로 쪼개져 있으므로 반드시 병합한 뒤 청킹해야 한다.
병합하지 않으면 중복 제거 단계에서 (제목, 섹션) 키가 겹쳐 조각들이 서로를 지운다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from wh40k.normalize import INTRO_SECTION

_RE_ROW = re.compile(r"^(?P<title>.+?) - (?P<section>.+?): (?P<body>.+)$", re.DOTALL)
_RE_TITLE_KEY = re.compile(r"[^a-z0-9]+")

# 본문 가치가 없는 섹션 (normalize 의 목록과 같은 기준)
_BOILERPLATE = {
    "sources",
    "source",
    "see also",
    "references",
    "external links",
    "gallery",
    "notes",
    "further reading",
    "related articles",
    "videos",
    "video",
    "images",
    "media",
}


def _title_key(title: str) -> str:
    return _RE_TITLE_KEY.sub(" ", title.lower()).strip()


def parse_row(row: str) -> tuple[str, str, str] | None:
    """한 행을 (제목, 섹션, 본문) 으로 나눈다. 쓸 수 없는 행은 None."""
    match = _RE_ROW.match(row.strip())
    if not match:
        return None

    title = match["title"].strip()
    section = match["section"].strip()
    body = match["body"].strip()

    if not body or section.lower() in _BOILERPLATE:
        return None

    # 도입부는 섹션명이 문서명으로 반복된다.
    if _title_key(section) == _title_key(title):
        section = INTRO_SECTION

    return title, section, body


def group_rows(rows: Iterable[str]) -> dict[str, list[tuple[str, str]]]:
    """행 목록을 문서별 (섹션, 본문) 목록으로 묶는다.

    같은 섹션의 조각은 순서대로 이어 붙인다. 섹션 순서는 처음 등장한 순서를 따른다.
    """
    documents: dict[str, dict[str, list[str]]] = {}

    for row in rows:
        parsed = parse_row(row)
        if not parsed:
            continue
        title, section, body = parsed
        documents.setdefault(title, {}).setdefault(section, []).append(body)

    return {
        title: [(section, "\n\n".join(parts)) for section, parts in sections.items()]
        for title, sections in documents.items()
    }


def resolve_url(title: str, fandom_urls: dict[str, str]) -> str | None:
    """Fandom 문서 제목과 맞춰 출처 URL 을 찾는다. 없으면 None (링크 없이 인용)."""
    if title in fandom_urls:
        return fandom_urls[title]

    key = _title_key(title)
    for known, url in fandom_urls.items():
        if _title_key(known) == key:
            return url
    return None


def build_title_index(fandom_urls: dict[str, str]) -> dict[str, str]:
    """resolve_url 을 매 호출마다 전수 비교하지 않도록 정규화 키 사전을 만든다."""
    return {_title_key(title): url for title, url in fandom_urls.items()}


def resolve_url_indexed(title: str, index: dict[str, str]) -> str | None:
    """build_title_index() 로 만든 사전을 써서 O(1) 로 URL 을 찾는다."""
    return index.get(_title_key(title))
