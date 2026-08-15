"""프롬프트 조립 테스트.

원본은 전량 영어인데 답변은 질문 언어를 따라가야 하므로 언어 감지가 필요하다.
40k 는 팬 창작이 많아 환각 위험이 커서, 근거 밖 서술 금지를 프롬프트로 강제한다.
"""

from wh40k.prompt import build_context, build_messages, detect_language


class TestDetectLanguage:
    def test_korean_question_detected(self):
        assert detect_language("호루스 헤러시가 뭐야?") == "ko"

    def test_english_question_detected(self):
        assert detect_language("Why did Cadia fall?") == "en"

    def test_korean_with_english_proper_nouns_still_korean(self):
        # 40k 용어는 영어 그대로 쓰는 경우가 많다.
        assert detect_language("Abaddon이 이끈 Black Crusade는 몇 번이야?") == "ko"

    def test_english_with_one_korean_particle_still_english(self):
        assert detect_language("Who is Abaddon the Despoiler and what did he do?") == "en"

    def test_empty_question_defaults_to_english(self):
        assert detect_language("") == "en"


class TestBuildContext:
    def _hit(self, n, title="Cadia", section="History", text="It fell."):
        return {"title": title, "section": section, "text": text,
                "source_url": f"https://example.com/{n}"}

    def test_each_hit_numbered_from_one(self):
        context = build_context([self._hit(1), self._hit(2, title="Orks")])
        assert "[1]" in context
        assert "[2]" in context

    def test_title_and_section_included_for_grounding(self):
        context = build_context([self._hit(1)])
        assert "Cadia" in context
        assert "History" in context

    def test_body_text_included(self):
        assert "It fell." in build_context([self._hit(1)])

    def test_empty_hits_yield_empty_context(self):
        assert build_context([]) == ""


class TestBuildMessages:
    HITS = [{"title": "Cadia", "section": "History", "text": "It fell in 999.M41.",
             "source_url": "https://example.com/cadia"}]

    def test_korean_question_instructs_korean_answer(self):
        system, _ = build_messages("카디아는 왜 함락됐어?", self.HITS)
        assert "한국어" in system

    def test_english_question_instructs_english_answer(self):
        system, _ = build_messages("Why did Cadia fall?", self.HITS)
        assert "English" in system

    def test_system_prompt_forbids_unsupported_claims(self):
        system, _ = build_messages("Why did Cadia fall?", self.HITS)
        lowered = system.lower()
        assert "only" in lowered or "not" in lowered

    def test_system_prompt_requires_citation_markers(self):
        system, _ = build_messages("Why did Cadia fall?", self.HITS)
        assert "[1]" in system

    def test_user_message_contains_question_and_context(self):
        _, user = build_messages("Why did Cadia fall?", self.HITS)
        assert "Why did Cadia fall?" in user
        assert "It fell in 999.M41." in user

    def test_no_hits_still_produces_messages(self):
        system, user = build_messages("Why did Cadia fall?", [])
        assert system and user
