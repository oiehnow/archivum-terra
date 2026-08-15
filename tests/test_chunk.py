"""청킹 및 중복 제거 테스트.

토크나이저를 로컬에 두지 않으므로 길이는 문자 수로 근사한다
(영문 기준 대략 4자 ≈ 1토큰).
"""

from wh40k.chunk import Chunk, chunk_document, dedupe


INTRO = (
    "Cadia was a terrestrial planet classified as the Imperium's most important "
    "Fortress World before its destruction in ca. 999.M41."
)


def _doc(**kw):
    base = dict(
        title="Cadia",
        sections=[("Introduction", INTRO)],
        source_url="https://warhammer40k.fandom.com/wiki/Cadia",
        source="fandom",
    )
    base.update(kw)
    return base


class TestChunkDocument:
    def test_short_section_becomes_single_chunk(self):
        chunks = chunk_document(**_doc())
        assert len(chunks) == 1
        assert chunks[0].section == "Introduction"

    def test_title_is_prefixed_so_chunk_stands_alone(self):
        # 섹션 본문만으로는 무슨 문서인지 알 수 없어 검색 품질이 떨어진다.
        chunks = chunk_document(**_doc())
        assert chunks[0].text.startswith("Cadia — Introduction\n")
        assert INTRO in chunks[0].text

    def test_metadata_carried_onto_chunk(self):
        chunks = chunk_document(**_doc())
        assert chunks[0].title == "Cadia"
        assert chunks[0].source_url == "https://warhammer40k.fandom.com/wiki/Cadia"
        assert chunks[0].source == "fandom"

    def test_chunk_ids_are_unique_and_stable(self):
        sections = [("A", "x" * 200), ("B", "y" * 200)]
        first = chunk_document(**_doc(sections=sections))
        second = chunk_document(**_doc(sections=sections))
        assert [c.id for c in first] == [c.id for c in second]
        assert len({c.id for c in first}) == 2

    def test_long_section_split_into_multiple_chunks(self):
        body = "\n\n".join(f"Paragraph {i}. " + "word " * 120 for i in range(6))
        chunks = chunk_document(**_doc(sections=[("History", body)]), max_chars=1000)
        assert len(chunks) > 1
        assert all(len(c.text) <= 1400 for c in chunks)

    def test_split_happens_at_paragraph_boundary(self):
        body = "\n\n".join("P" + str(i) + ". " + "word " * 100 for i in range(5))
        chunks = chunk_document(**_doc(sections=[("History", body)]), max_chars=800)
        # 문단 중간에서 잘리면 조각난 단어가 생긴다
        for c in chunks:
            assert not c.text.endswith("wor")

    def test_split_chunks_share_section_name(self):
        body = "\n\n".join("word " * 150 for _ in range(5))
        chunks = chunk_document(**_doc(sections=[("History", body)]), max_chars=800)
        assert {c.section for c in chunks} == {"History"}

    def test_overlap_repeats_tail_of_previous_chunk(self):
        # 마커를 문단 끝에 둬야 "앞 청크의 꼬리"가 실제로 겹쳤는지 검증할 수 있다.
        body = "\n\n".join("word " * 100 + f"MARKER{i}" for i in range(4))
        chunks = chunk_document(**_doc(sections=[("H", body)]), max_chars=700, overlap=300)
        assert len(chunks) > 1
        assert "MARKER0" in chunks[0].text
        assert "MARKER0" in chunks[1].text

    def test_no_overlap_when_disabled(self):
        body = "\n\n".join("word " * 100 + f"MARKER{i}" for i in range(4))
        chunks = chunk_document(**_doc(sections=[("H", body)]), max_chars=700, overlap=0)
        assert "MARKER0" not in chunks[1].text

    def test_too_short_section_dropped(self):
        chunks = chunk_document(**_doc(sections=[("Stub", "tiny")]), min_chars=50)
        assert chunks == []

    def test_empty_document_yields_nothing(self):
        assert chunk_document(**_doc(sections=[])) == []


class TestDedupe:
    def _c(self, title, section, source, url=None):
        return Chunk(
            id=f"{source}:{title}:{section}",
            title=title,
            section=section,
            text=f"{title} — {section}\nbody",
            source_url=url,
            source=source,
        )

    def test_identical_title_and_section_deduplicated(self):
        chunks = [self._c("Cadia", "History", "fandom"), self._c("Cadia", "History", "hf")]
        assert len(dedupe(chunks)) == 1

    def test_fandom_wins_over_hf(self):
        # Fandom 쪽만 출처 URL 을 가지므로 인용 링크를 살리려면 이쪽이 남아야 한다.
        chunks = [self._c("Cadia", "History", "hf"), self._c("Cadia", "History", "fandom")]
        assert dedupe(chunks)[0].source == "fandom"

    def test_title_matching_ignores_case_and_underscores(self):
        chunks = [
            self._c("Horus Heresy", "Intro", "fandom"),
            self._c("horus_heresy", "intro", "hf"),
        ]
        assert len(dedupe(chunks)) == 1

    def test_different_sections_both_kept(self):
        chunks = [self._c("Cadia", "History", "fandom"), self._c("Cadia", "Legacy", "fandom")]
        assert len(dedupe(chunks)) == 2

    def test_hf_only_document_is_kept(self):
        chunks = [self._c("Obscure Planet", "Intro", "hf")]
        assert len(dedupe(chunks)) == 1

    def test_original_order_preserved(self):
        chunks = [
            self._c("A", "s", "fandom"),
            self._c("B", "s", "fandom"),
            self._c("C", "s", "fandom"),
        ]
        assert [c.title for c in dedupe(chunks)] == ["A", "B", "C"]
