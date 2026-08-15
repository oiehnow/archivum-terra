"""wikitext → 평문 정규화 테스트.

실제 Fandom 40k 위키(Cadia 등)에서 관찰된 마크업 패턴을 기준으로 한다.
"""

from wh40k.normalize import is_redirect, split_sections, strip_wikitext


class TestIsRedirect:
    def test_redirect_page_detected(self):
        assert is_redirect("#REDIRECT [[Orks]]") is True

    def test_lowercase_redirect_detected(self):
        assert is_redirect("#redirect [[Orks]]") is True

    def test_normal_article_is_not_redirect(self):
        assert is_redirect("Cadia was a fortress world.") is False


class TestRedirectSections:
    def test_redirect_page_yields_no_sections(self):
        assert split_sections("#REDIRECT [[Orks]]") == []


class TestStripWikitext:
    def test_plain_link_keeps_only_target_text(self):
        assert strip_wikitext("guarded by [[Terra]] forces") == "guarded by Terra forces"

    def test_piped_link_keeps_display_text(self):
        assert (
            strip_wikitext("the [[Imperium of Man|Imperium]] fell")
            == "the Imperium fell"
        )

    def test_bold_and_italic_markup_removed(self):
        assert strip_wikitext("'''Cadia''', also ''known'' as") == "Cadia, also known as"

    def test_file_link_removed_entirely(self):
        assert strip_wikitext("[[File:Cadia.jpg|center|210px]]text") == "text"

    def test_infobox_template_removed(self):
        wikitext = "{{Planet\n|title1=Cadia Prime\n|gravity=1.12 G\n}}\nCadia was a planet."
        assert strip_wikitext(wikitext) == "Cadia was a planet."

    def test_quote_template_removed(self):
        wikitext = "{{Quote|This is Cadia!| Inquisitor-General Neve}}\nCadia was fortified."
        assert strip_wikitext(wikitext) == "Cadia was fortified."

    def test_nested_template_removed(self):
        assert strip_wikitext("{{Outer|{{Inner|x}}|y}}kept") == "kept"

    def test_br_tag_becomes_space(self):
        assert strip_wikitext("Chaos <br> Imperium <br />Eldar") == "Chaos Imperium Eldar"

    def test_ref_tag_and_contents_removed(self):
        assert strip_wikitext("fact<ref>Codex: Astra Militarum</ref> stated") == "fact stated"

    def test_self_closing_ref_removed(self):
        assert strip_wikitext("fact<ref name='a' /> stated") == "fact stated"

    def test_html_comment_removed(self):
        assert strip_wikitext("before<!-- hidden note -->after") == "beforeafter"

    def test_list_bullet_markers_removed(self):
        assert strip_wikitext("* first\n* second") == "first\nsecond"

    def test_blank_lines_collapsed(self):
        assert strip_wikitext("para one\n\n\n\npara two") == "para one\n\npara two"

    def test_external_link_keeps_label(self):
        assert strip_wikitext("see [https://example.com the source] now") == "see the source now"

    def test_category_link_removed(self):
        assert strip_wikitext("body text\n[[Category:Planets]]") == "body text"

    def test_wiki_table_removed(self):
        # 표는 평문화하면 셀 구분이 사라져 노이즈가 되므로 블록째 제거한다.
        wikitext = 'before\n{| class="wikitable"\n! head\n| align="center" |cell\n|}\nafter'
        assert strip_wikitext(wikitext) == "before\nafter"

    def test_unclosed_wikilink_brackets_removed(self):
        # 원본에 실제로 존재하는 마크업 오류: [[ 가 닫히지 않음
        assert strip_wikitext("fleet of [[Shadrak Meduson's force") == "fleet of Shadrak Meduson's force"

    def test_unbalanced_bold_markup_removed(self):
        assert strip_wikitext("Lazlo Tiberius'''Master of the Fleet'''10 Barges'15 Cruisers") == (
            "Lazlo TiberiusMaster of the Fleet10 Barges'15 Cruisers"
        )

    def test_gallery_contents_removed_not_just_tags(self):
        # gallery 내부는 [[...]] 없이 "File:x" 로 나열되어 위키링크 노드가 아니다.
        wikitext = "before\n<gallery>\nFile:Cadia.jpg|caption\nFile:Pylon.jpg\n</gallery>\nafter"
        assert strip_wikitext(wikitext) == "before\nafter"


class TestSplitSections:
    def test_text_before_any_heading_is_intro_section(self):
        sections = split_sections("Cadia was a fortress world.")
        assert sections == [("Introduction", "Cadia was a fortress world.")]

    def test_heading_starts_new_section(self):
        wikitext = "Intro text.\n== History ==\nIt was destroyed."
        assert split_sections(wikitext) == [
            ("Introduction", "Intro text."),
            ("History", "It was destroyed."),
        ]

    def test_subsection_heading_recognised(self):
        wikitext = "== History ==\nmain\n=== Early History ===\ndetail"
        assert split_sections(wikitext) == [
            ("History", "main"),
            ("Early History", "detail"),
        ]

    def test_empty_section_dropped(self):
        wikitext = "Intro.\n== Gallery ==\n\n== History ==\nreal content"
        assert split_sections(wikitext) == [
            ("Introduction", "Intro."),
            ("History", "real content"),
        ]

    def test_boilerplate_sections_dropped(self):
        wikitext = "Intro.\n== Sources ==\nCodex p.42\n== See Also ==\n[[Terra]]"
        assert split_sections(wikitext) == [("Introduction", "Intro.")]

    def test_media_only_sections_dropped(self):
        wikitext = "Intro.\n== Videos ==\nFile:Lore Part 38\n== History ==\nreal content"
        assert split_sections(wikitext) == [
            ("Introduction", "Intro."),
            ("History", "real content"),
        ]

    def test_document_with_no_intro_starts_at_first_heading(self):
        assert split_sections("== History ==\nIt fell.") == [("History", "It fell.")]
