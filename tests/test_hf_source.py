"""HF 보조 데이터셋(vizn3r/warhammer40k-lore) 파서 테스트.

형식은 "{제목} - {섹션}: {본문}" 한 줄이다. 출처 URL 이 없으므로
Fandom 문서 제목과 맞춰 링크를 역으로 채운다.
"""

from wh40k.hf_source import group_rows, parse_row, resolve_url


class TestParseRow:
    def test_splits_title_section_and_body(self):
        assert parse_row("Cadia - History: It fell in 999.M41.") == (
            "Cadia", "History", "It fell in 999.M41.")

    def test_section_equal_to_title_becomes_introduction(self):
        # 도입부는 섹션명이 문서명으로 반복된다.
        title, section, _ = parse_row("Age of Apostasy - Age of Apostasy: It was a civil war.")
        assert (title, section) == ("Age of Apostasy", "Introduction")

    def test_title_with_parentheses_preserved(self):
        title, section, _ = parse_row("Agathon (Deathwatch) - Chalnath Campaign: For the servants.")
        assert title == "Agathon (Deathwatch)"
        assert section == "Chalnath Campaign"

    def test_colon_inside_body_kept(self):
        # 첫 콜론에서만 자르고, 본문에 남은 콜론은 건드리지 않는다.
        _, _, body = parse_row("Leman Russ - Armament: Main gun: battle cannon, 120mm")
        assert body == "Main gun: battle cannon, 120mm"

    def test_apostrophe_in_section_preserved(self):
        _, section, _ = parse_row("Agathon - Battle of Saint's Halt: The Shrine World.")
        assert section == "Battle of Saint's Halt"

    def test_boilerplate_section_rejected(self):
        assert parse_row("Agathean Domain - Sources: Codex: Imperial Guard, pg. 23") is None

    def test_malformed_row_rejected(self):
        assert parse_row("no separators here") is None

    def test_empty_body_rejected(self):
        assert parse_row("Cadia - History: ") is None


class TestGroupRows:
    def test_rows_grouped_by_title(self):
        rows = ["Cadia - History: fell", "Orks - Biology: fungal"]
        grouped = group_rows(rows)
        assert set(grouped) == {"Cadia", "Orks"}

    def test_repeated_section_merged_into_one(self):
        # 같은 섹션이 여러 조각으로 나뉘어 있다. 합치지 않으면
        # 중복 제거 단계에서 조각들이 서로를 지운다.
        rows = [
            "Age of Apostasy - Reign of Blood: first part",
            "Age of Apostasy - Seeds of Heresy: unrelated",
            "Age of Apostasy - Reign of Blood: second part",
        ]
        sections = dict(group_rows(rows)["Age of Apostasy"])
        assert sections["Reign of Blood"] == "first part\n\nsecond part"

    def test_section_order_follows_first_appearance(self):
        rows = [
            "X - Beta: b",
            "X - Alpha: a",
            "X - Beta: b2",
        ]
        assert [s for s, _ in group_rows(rows)["X"]] == ["Beta", "Alpha"]

    def test_unparseable_rows_skipped(self):
        assert group_rows(["garbage", "Cadia - History: fell"]) == {
            "Cadia": [("History", "fell")]}


class TestResolveUrl:
    FANDOM = {"Cadia": "https://warhammer40k.fandom.com/wiki/Cadia"}

    def test_exact_title_match_returns_url(self):
        assert resolve_url("Cadia", self.FANDOM) == "https://warhammer40k.fandom.com/wiki/Cadia"

    def test_case_and_underscore_differences_tolerated(self):
        assert resolve_url("cadia", self.FANDOM) is not None

    def test_unmatched_title_returns_none(self):
        # Fandom 에 없는 문서는 링크 없이 인용한다.
        assert resolve_url("Obscure Planet", self.FANDOM) is None
