"""임베딩 모델 설정 테스트.

e5 계열은 질의에 "query: ", 문서에 "passage: " 접두어를 붙여야 한다.
빠뜨려도 오류가 나지 않고 검색 품질만 조용히 나빠지므로 테스트로 고정한다.
"""

import pytest

from wh40k.embedding import EMBED_MODELS, doc_text, get_config, query_text


class TestGetConfig:
    def test_known_model_returns_config(self):
        assert get_config("intfloat/multilingual-e5-small").dim == 384

    def test_bge_m3_config(self):
        assert get_config("BAAI/bge-m3").dim == 1024

    def test_unknown_model_rejected(self):
        # 접두어 규칙을 모르는 모델을 조용히 쓰면 품질이 무너진다.
        with pytest.raises(KeyError):
            get_config("some/unregistered-model")

    def test_every_registered_model_declares_dim(self):
        assert all(cfg.dim > 0 for cfg in EMBED_MODELS.values())


class TestPrefixes:
    E5 = "intfloat/multilingual-e5-small"
    BGE = "BAAI/bge-m3"

    def test_e5_query_gets_query_prefix(self):
        assert query_text("카디아", self.E5) == "query: 카디아"

    def test_e5_document_gets_passage_prefix(self):
        assert doc_text("Cadia fell.", self.E5) == "passage: Cadia fell."

    def test_bge_needs_no_prefix(self):
        assert query_text("카디아", self.BGE) == "카디아"
        assert doc_text("Cadia fell.", self.BGE) == "Cadia fell."

    def test_query_and_document_prefixes_differ_for_e5(self):
        # 같은 접두어를 쓰면 e5 의 비대칭 검색 성능이 사라진다.
        assert query_text("x", self.E5) != doc_text("x", self.E5)
