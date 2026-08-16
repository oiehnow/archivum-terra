"""하이브리드 검색 융합 테스트.

벡터 검색은 의미가 비슷한 문서를, BM25 는 고유명사가 정확히 일치하는 문서를 찾는다.
40k 로어는 고유명사(Cadia, Horus, Krieg)가 핵심이라 둘 다 필요하다.
점수 체계가 서로 다르므로 순위만 사용하는 RRF 로 합친다.
"""

from wh40k.retrieve import (
    OFF_TOPIC_DISTANCE,
    drop_unmatched,
    is_off_topic,
    merge_adjacent,
    reciprocal_rank_fusion,
)


class TestIsOffTopic:
    """벡터 검색은 아무 질문에나 가장 가까운 문서를 돌려준다.

    "손흥민 골 기록" 에도 문서가 잡히므로, 그대로 두면 무관한 근거로 답을 지어낸다.
    상위 하나만 보면 우연히 가까운 문서에 휘둘리므로 상위 여러 개의 평균으로 판단한다.
    (실측: 40k 질문 top-8 평균 최대 1.014, 무관한 질문 최소 1.071)
    """

    def test_close_distances_are_on_topic(self):
        assert is_off_topic([0.61, 0.72, 0.80, 0.83]) is False

    def test_far_distances_are_off_topic(self):
        assert is_off_topic([1.12, 1.15, 1.20, 1.26]) is True

    def test_borderline_40k_question_stays_on_topic(self):
        # "호루스 헤러시가 뭐야?" 실측값 근처
        assert is_off_topic([1.00, 1.01, 1.01, 1.02]) is False

    def test_single_near_hit_does_not_rescue_off_topic_query(self):
        # "오늘 점심 뭐 먹지?" 는 음식 문서 하나가 가깝지만 나머지는 멀다
        assert is_off_topic([0.97, 1.06, 1.08, 1.09, 1.10]) is True

    def test_empty_distances_are_off_topic(self):
        assert is_off_topic([]) is True

    def test_threshold_sits_between_measured_ranges(self):
        assert 1.0143 < OFF_TOPIC_DISTANCE < 1.0706


class TestDropUnmatched:
    """BM25 는 매칭 토큰이 없어도 문서를 순서대로 돌려준다.

    한국어 질의는 영어 인덱스와 한 토큰도 겹치지 않아 전부 0점이 나오는데,
    이를 걸러내지 않으면 RRF 가 무의미한 순위를 벡터 결과와 동등하게 섞는다.
    """

    def test_zero_scored_results_dropped(self):
        assert drop_unmatched(["a", "b", "c"], [0.0, 0.0, 0.0]) == []

    def test_all_zero_from_korean_query_yields_empty(self):
        # 실제 증상: 한국어 질문마다 인덱스 첫 문서들이 상위에 붙었다.
        assert drop_unmatched(["first_doc", "second_doc"], [0.0, 0.0]) == []

    def test_positive_scores_kept(self):
        assert drop_unmatched(["a", "b"], [5.5, 5.1]) == ["a", "b"]

    def test_only_zero_tail_dropped(self):
        assert drop_unmatched(["a", "b", "c"], [5.5, 0.0, 0.0]) == ["a"]

    def test_order_preserved(self):
        assert drop_unmatched(["x", "y", "z"], [3.0, 9.0, 1.0]) == ["x", "y", "z"]

    def test_length_mismatch_is_safe(self):
        assert drop_unmatched(["a", "b"], [1.0]) == ["a"]


class TestReciprocalRankFusion:
    def test_document_ranked_first_by_both_wins(self):
        fused = reciprocal_rank_fusion([["a", "b", "c"], ["a", "c", "b"]])
        assert fused[0][0] == "a"

    def test_document_found_by_both_beats_one_ranked_higher_by_only_one(self):
        # b 는 어느 쪽에서도 1위가 아니지만 양쪽에 모두 있어 종합 점수가 높다.
        fused = reciprocal_rank_fusion([["a", "b"], ["c", "b"]])
        assert fused[0][0] == "b"

    def test_scores_are_descending(self):
        fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "a", "c"]])
        scores = [s for _, s in fused]
        assert scores == sorted(scores, reverse=True)

    def test_top_n_limits_result_count(self):
        fused = reciprocal_rank_fusion([list("abcdefghij")], top_n=3)
        assert len(fused) == 3

    def test_empty_ranking_ignored(self):
        assert [d for d, _ in reciprocal_rank_fusion([[], ["a", "b"]])] == ["a", "b"]

    def test_no_rankings_yields_empty(self):
        assert reciprocal_rank_fusion([]) == []

    def test_smaller_k_sharpens_rank_one_advantage(self):
        # k 가 작을수록 상위 순위의 가중치가 커진다.
        rankings = [["a", "b"], ["b", "a"]]
        assert reciprocal_rank_fusion(rankings, k=1)[0][1] > reciprocal_rank_fusion(rankings, k=60)[0][1]

    def test_duplicate_within_single_ranking_counted_once(self):
        fused = dict(reciprocal_rank_fusion([["a", "a", "b"]]))
        assert fused["a"] == fused["a"]  # 중복이 점수를 부풀리지 않아야 한다
        single = dict(reciprocal_rank_fusion([["a", "b"]]))
        assert fused["a"] == single["a"]


class TestMergeAdjacent:
    def _hit(self, title, section, text):
        return {"title": title, "section": section, "text": text}

    def test_same_document_sections_merged(self):
        hits = [
            self._hit("Cadia", "History", "It fell."),
            self._hit("Cadia", "Legacy", "Cadians endure."),
        ]
        merged = merge_adjacent(hits)
        assert len(merged) == 1
        assert "It fell." in merged[0]["text"]
        assert "Cadians endure." in merged[0]["text"]

    def test_different_documents_not_merged(self):
        hits = [self._hit("Cadia", "History", "a"), self._hit("Orks", "Biology", "b")]
        assert len(merge_adjacent(hits)) == 2

    def test_merged_entry_keeps_first_rank_position(self):
        hits = [
            self._hit("Orks", "Biology", "b"),
            self._hit("Cadia", "History", "a"),
            self._hit("Cadia", "Legacy", "c"),
        ]
        assert [h["title"] for h in merge_adjacent(hits)] == ["Orks", "Cadia"]

    def test_sections_listed_in_merged_entry(self):
        hits = [
            self._hit("Cadia", "History", "a"),
            self._hit("Cadia", "Legacy", "c"),
        ]
        assert merge_adjacent(hits)[0]["section"] == "History; Legacy"

    def test_empty_input_yields_empty(self):
        assert merge_adjacent([]) == []
