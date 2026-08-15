"""wikitext → 평문 정규화 및 섹션 분해.

mwparserfromhell 의 strip_code() 는 링크·템플릿·볼드까지는 정확히 처리하지만
File/Category 링크, <ref> 본문, 리스트 마커는 잔여물을 남긴다. 전처리와 후처리로 보완한다.
"""

from __future__ import annotations

import re

import mwparserfromhell as mw

# strip_code() 가 손대지 않는 HTML 계열 태그들
_RE_REF_PAIR = re.compile(r"<ref[^>]*>.*?</ref>", re.DOTALL | re.IGNORECASE)
_RE_REF_SELF = re.compile(r"<ref[^>]*/\s*>", re.IGNORECASE)
_RE_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_RE_BR = re.compile(r"<br\s*/?\s*>", re.IGNORECASE)
# gallery/imagemap 내부는 "File:x|caption" 나열이라 위키링크 노드가 아니다.
# 태그만 벗기면 파일명이 본문에 섞이므로 내용째 제거한다.
# 앞쪽 개행까지 함께 흡수해 블록이 있던 자리에 빈 줄이 남지 않게 한다.
_RE_MEDIA_BLOCK = re.compile(
    r"\n?[ \t]*<(gallery|imagemap|timeline)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE
)
_RE_TAG = re.compile(r"</?(?:small|sup|sub|center|div|span|poem)[^>]*>", re.IGNORECASE)
# gallery 밖에 홀로 남은 "File:..." / "Image:..." 줄 (닫는 태그가 없는 문서에서 발생)
_RE_BARE_FILE_LINE = re.compile(r"^[ \t]*(?:File|Image):.*\n?", re.MULTILINE | re.IGNORECASE)

# 후처리
# strip_code() 가 리스트 마커를 먼저 지우고 들여쓰기 공백만 남기는 경우가 있어
# 마커 제거와 줄 앞 공백 제거를 함께 둔다.
_RE_LIST_MARKER = re.compile(r"^[ \t]*[*#:;]+[ \t]*", re.MULTILINE)
_RE_LEADING_WS = re.compile(r"^[ \t]+", re.MULTILINE)
_RE_TRAILING_WS = re.compile(r"[ \t]+$", re.MULTILINE)
_RE_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_RE_MULTI_BLANK = re.compile(r"\n{3,}")

# 본문 가치가 없는 섹션 (인덱싱에서 제외)
_BOILERPLATE_SECTIONS = {
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

# 본문이 아닌 위키링크 네임스페이스
_NON_CONTENT_NS = ("file:", "image:", "category:", "media:")

_RE_HEADING = re.compile(r"^\s*(={2,6})\s*(.+?)\s*\1\s*$", re.MULTILINE)
_RE_REDIRECT = re.compile(r"^\s*#\s*REDIRECT\b", re.IGNORECASE)

# 표는 평문화하면 셀 경계가 사라져 문장이 뒤엉키므로 블록째 제거한다.
_RE_TABLE = re.compile(r"\n?[ \t]*\{\|.*?\n[ \t]*\|\}", re.DOTALL)

# 원본 마크업 오류(닫히지 않은 링크, 짝 안 맞는 볼드)로 남은 잔여물 정리
_RE_LEFTOVER_BRACKETS = re.compile(r"\[\[|\]\]")
_RE_LEFTOVER_BOLD = re.compile(r"'{3,}")

INTRO_SECTION = "Introduction"


def is_redirect(wikitext: str) -> bool:
    """`#REDIRECT [[대상]]` 형태의 넘겨주기 문서인지 판별한다."""
    return bool(_RE_REDIRECT.match(wikitext))


def strip_wikitext(wikitext: str) -> str:
    """wikitext 를 읽기 가능한 평문으로 변환한다."""
    text = _RE_COMMENT.sub("", wikitext)
    text = _RE_REF_PAIR.sub("", text)
    text = _RE_REF_SELF.sub("", text)
    text = _RE_MEDIA_BLOCK.sub("", text)
    text = _RE_TABLE.sub("", text)
    text = _RE_BR.sub(" ", text)
    text = _RE_TAG.sub("", text)
    text = _RE_BARE_FILE_LINE.sub("", text)

    code = mw.parse(text)

    # File/Category 링크는 표시 텍스트가 본문이 아니므로 노드째 제거한다.
    for link in code.filter_wikilinks():
        if str(link.title).strip().lower().startswith(_NON_CONTENT_NS):
            try:
                code.remove(link)
            except ValueError:
                # 다른 노드 안에 중첩된 경우 strip_code() 가 처리하도록 둔다.
                pass

    text = code.strip_code(normalize=True, collapse=True)

    # strip_code() 는 짝이 맞는 마크업만 처리한다. 원본 오류로 남은 것을 정리한다.
    text = _RE_LEFTOVER_BRACKETS.sub("", text)
    text = _RE_LEFTOVER_BOLD.sub("", text)

    text = _RE_LIST_MARKER.sub("", text)
    text = _RE_LEADING_WS.sub("", text)
    text = _RE_MULTI_SPACE.sub(" ", text)
    text = _RE_TRAILING_WS.sub("", text)
    text = _RE_MULTI_BLANK.sub("\n\n", text)
    return text.strip()


def split_sections(wikitext: str) -> list[tuple[str, str]]:
    """`== 제목 ==` 기준으로 (섹션명, 평문) 목록을 만든다.

    첫 제목 앞의 도입부는 "Introduction" 으로 둔다.
    넘겨주기 문서, 내용이 비었거나 정보 가치가 없는 섹션은 제외한다.
    """
    if is_redirect(wikitext):
        return []

    matches = list(_RE_HEADING.finditer(wikitext))

    raw: list[tuple[str, str]] = []
    intro = wikitext[: matches[0].start()] if matches else wikitext
    raw.append((INTRO_SECTION, intro))

    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(wikitext)
        raw.append((match.group(2), wikitext[match.end() : end]))

    sections: list[tuple[str, str]] = []
    for title, body in raw:
        clean_title = strip_wikitext(title)
        if clean_title.lower() in _BOILERPLATE_SECTIONS:
            continue
        clean_body = strip_wikitext(body)
        if not clean_body:
            continue
        sections.append((clean_title, clean_body))
    return sections
