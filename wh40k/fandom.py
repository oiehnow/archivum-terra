"""Warhammer 40k Fandom 위키 수집기.

네트워크 호출은 주입 가능한 fetch 함수로 분리했다. URL 조립·응답 파싱·페이징은
순수 로직이라 네트워크 없이 검증된다.

수집량은 본문 문서 약 7,300개. 목록 15회 + 본문 146회, 총 160여 회 요청이면 끝난다.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from wh40k.normalize import is_redirect

WIKI = "https://warhammer40k.fandom.com"
API_URL = f"{WIKI}/api.php"

# 위키 예의: 신원을 밝히고 간격을 둔다.
USER_AGENT = "ArchivumTerra/0.1 (lore RAG research; contact via HF: oiehnow)"
REQUEST_DELAY = 0.4

# MediaWiki 가 한 번에 받아주는 pageids 개수
MAX_PAGEIDS_PER_REQUEST = 50
LISTING_PAGE_SIZE = 500

Fetch = Callable[[str, dict[str, str]], dict]


@dataclass(frozen=True)
class Page:
    pageid: int
    title: str
    revid: int
    wikitext: str
    url: str


def article_url(title: str) -> str:
    """문서 제목을 사람이 열 수 있는 위키 URL 로 만든다 (인용 링크에 쓴다)."""
    slug = urllib.parse.quote(title.replace(" ", "_"), safe="")
    return f"{WIKI}/wiki/{slug}"


def listing_params(continue_token: str | None = None) -> dict[str, str]:
    """본문 네임스페이스의 비-리다이렉트 문서 목록을 요청하는 파라미터."""
    params = {
        "action": "query",
        "format": "json",
        "generator": "allpages",
        "gapnamespace": "0",
        "gapfilterredir": "nonredirects",
        "gaplimit": str(LISTING_PAGE_SIZE),
    }
    if continue_token:
        params["gapcontinue"] = continue_token
    return params


def parse_listing(payload: dict) -> tuple[list[tuple[int, str]], str | None]:
    """목록 응답에서 (pageid, title) 목록과 다음 페이징 토큰을 뽑는다."""
    pages = [
        (int(p["pageid"]), p["title"])
        for p in payload.get("query", {}).get("pages", {}).values()
        if "pageid" in p
    ]
    return pages, payload.get("continue", {}).get("gapcontinue")


def revision_params(pageids: list[int]) -> dict[str, str]:
    """여러 문서의 wikitext 를 한 번에 받아오는 파라미터."""
    if len(pageids) > MAX_PAGEIDS_PER_REQUEST:
        raise ValueError(f"한 번에 {MAX_PAGEIDS_PER_REQUEST}개까지만 요청할 수 있다")
    return {
        "action": "query",
        "format": "json",
        "prop": "revisions",
        "rvprop": "content|ids",
        "rvslots": "main",
        "pageids": "|".join(str(i) for i in pageids),
    }


def parse_revisions(payload: dict) -> list[Page]:
    """본문 응답을 Page 목록으로 바꾼다. 리다이렉트와 결측 문서는 버린다."""
    pages: list[Page] = []
    for raw in payload.get("query", {}).get("pages", {}).values():
        revisions = raw.get("revisions")
        if not revisions or "pageid" not in raw:
            continue

        revision = revisions[0]
        wikitext = revision.get("slots", {}).get("main", {}).get("*", "")
        if not wikitext or is_redirect(wikitext):
            continue

        pages.append(
            Page(
                pageid=int(raw["pageid"]),
                title=raw["title"],
                revid=int(revision.get("revid", 0)),
                wikitext=wikitext,
                url=article_url(raw["title"]),
            )
        )
    return pages


def fetch_all_pages(fetch: Fetch, max_requests: int = 200) -> list[tuple[int, str]]:
    """페이징을 따라가며 전체 문서 목록을 모은다.

    max_requests 는 API 가 계속 continue 를 돌려줄 때를 대비한 안전장치다.
    """
    collected: list[tuple[int, str]] = []
    token: str | None = None

    for _ in range(max_requests):
        payload = fetch(API_URL, listing_params(token))
        pages, token = parse_listing(payload)
        collected.extend(pages)
        if not token:
            break
    return collected


def fetch_pages_content(
    fetch: Fetch,
    pageids: list[int],
    on_batch: Callable[[list[Page]], None] | None = None,
) -> Iterator[Page]:
    """문서 본문을 50개씩 배치로 받아온다."""
    for start in range(0, len(pageids), MAX_PAGEIDS_PER_REQUEST):
        batch = pageids[start : start + MAX_PAGEIDS_PER_REQUEST]
        pages = parse_revisions(fetch(API_URL, revision_params(batch)))
        if on_batch:
            on_batch(pages)
        yield from pages


def http_fetch(url: str, params: dict[str, str]) -> dict:
    """실제 네트워크 호출. 429/503 에는 물러섰다가 다시 시도한다."""
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": USER_AGENT})

    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            time.sleep(REQUEST_DELAY)
            return payload
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503) or attempt == 4:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")
