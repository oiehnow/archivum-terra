"""Fandom MediaWiki API 수집기 테스트.

네트워크 호출은 주입한 fetch 함수로 대체한다.
URL 조립·응답 파싱·페이징·이어받기 판단은 모두 순수 로직으로 검증한다.
"""

import pytest

from wh40k.fandom import (
    API_URL,
    Page,
    article_url,
    fetch_all_pages,
    listing_params,
    parse_listing,
    parse_revisions,
    revision_params,
)


class TestArticleUrl:
    def test_spaces_become_underscores(self):
        assert article_url("Horus Heresy") == "https://warhammer40k.fandom.com/wiki/Horus_Heresy"

    def test_special_characters_percent_encoded(self):
        assert article_url("Bel'akor") == "https://warhammer40k.fandom.com/wiki/Bel%27akor"

    def test_slash_in_title_encoded_not_treated_as_path(self):
        assert article_url("A/B") == "https://warhammer40k.fandom.com/wiki/A%2FB"


class TestListingParams:
    def test_requests_main_namespace_articles_only(self):
        params = listing_params()
        assert params["gapnamespace"] == "0"
        assert params["gapfilterredir"] == "nonredirects"

    def test_continuation_token_included_when_given(self):
        assert listing_params("Next Page")["gapcontinue"] == "Next Page"

    def test_no_continuation_key_on_first_call(self):
        assert "gapcontinue" not in listing_params()


class TestParseListing:
    def test_extracts_page_ids_and_titles(self):
        payload = {"query": {"pages": {
            "38": {"pageid": 38, "title": "Horus Heresy"},
            "12": {"pageid": 12, "title": "Cadia"},
        }}}
        pages, cont = parse_listing(payload)
        assert sorted(pages) == [(12, "Cadia"), (38, "Horus Heresy")]
        assert cont is None

    def test_returns_continuation_token(self):
        payload = {"query": {"pages": {}}, "continue": {"gapcontinue": "Dark Angels"}}
        _, cont = parse_listing(payload)
        assert cont == "Dark Angels"

    def test_empty_response_yields_no_pages(self):
        assert parse_listing({}) == ([], None)


class TestRevisionParams:
    def test_batches_page_ids_into_pipe_separated_string(self):
        assert revision_params([1, 2, 3])["pageids"] == "1|2|3"

    def test_rejects_batch_larger_than_api_limit(self):
        with pytest.raises(ValueError, match="50"):
            revision_params(list(range(51)))


class TestParseRevisions:
    def _payload(self, wikitext):
        return {"query": {"pages": {"12": {
            "pageid": 12, "title": "Cadia",
            "revisions": [{"revid": 900, "slots": {"main": {"*": wikitext}}}],
        }}}}

    def test_extracts_page_with_wikitext(self):
        pages = parse_revisions(self._payload("Cadia was a fortress world."))
        assert pages == [Page(
            pageid=12, title="Cadia", revid=900,
            wikitext="Cadia was a fortress world.",
            url="https://warhammer40k.fandom.com/wiki/Cadia",
        )]

    def test_redirect_page_excluded(self):
        assert parse_revisions(self._payload("#REDIRECT [[Orks]]")) == []

    def test_page_without_revisions_skipped(self):
        payload = {"query": {"pages": {"12": {"pageid": 12, "title": "Cadia"}}}}
        assert parse_revisions(payload) == []

    def test_missing_page_skipped(self):
        payload = {"query": {"pages": {"-1": {"title": "Nope", "missing": ""}}}}
        assert parse_revisions(payload) == []


class TestFetchAllPages:
    def test_follows_continuation_until_exhausted(self):
        calls = []

        def fake_fetch(url, params):
            calls.append(params)
            assert url == API_URL
            if "gapcontinue" not in params:
                return {"query": {"pages": {"1": {"pageid": 1, "title": "A"}}},
                        "continue": {"gapcontinue": "B"}}
            return {"query": {"pages": {"2": {"pageid": 2, "title": "B"}}}}

        pages = fetch_all_pages(fake_fetch)
        assert sorted(pages) == [(1, "A"), (2, "B")]
        assert len(calls) == 2

    def test_stops_at_max_pages_guard(self):
        def endless_fetch(url, params):
            return {"query": {"pages": {"1": {"pageid": 1, "title": "A"}}},
                    "continue": {"gapcontinue": "again"}}

        # 무한 루프 방지 장치가 없으면 이 테스트는 끝나지 않는다.
        pages = fetch_all_pages(endless_fetch, max_requests=3)
        assert len(pages) <= 3
