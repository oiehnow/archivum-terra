"""검색 결과를 근거로 답변을 만들기 위한 프롬프트 조립.

두 가지 제약이 설계를 좌우한다.

1. 원본 자료는 전량 영어인데 답변은 질문 언어를 따라가야 한다.
2. 40k 는 팬 창작과 추측이 방대해 모델이 그럴듯한 거짓을 지어내기 쉽다.
   근거에 없으면 없다고 답하도록 프롬프트로 강제하고, 문장마다 인용을 요구한다.
"""

from __future__ import annotations

import re

_RE_HANGUL = re.compile(r"[가-힣]")

LANGUAGE_NAMES = {"ko": "한국어", "en": "English"}


def detect_language(question: str) -> str:
    """질문 언어를 판별한다. 한글이 하나라도 있으면 한국어로 본다.

    40k 용어는 한국어 질문에서도 영어 그대로 쓰이는 경우가 많아
    (예: "Abaddon이 이끈 Black Crusade") 비율이 아니라 존재로 판단한다.
    """
    return "ko" if _RE_HANGUL.search(question) else "en"


def build_context(hits: list[dict]) -> str:
    """검색 결과를 번호가 붙은 근거 블록으로 만든다."""
    blocks = []
    for number, hit in enumerate(hits, start=1):
        blocks.append(
            f"[{number}] {hit['title']} — {hit['section']}\n{hit['text']}"
        )
    return "\n\n".join(blocks)


def build_messages(question: str, hits: list[dict]) -> tuple[str, str]:
    """(시스템 프롬프트, 사용자 메시지) 를 만든다."""
    language = detect_language(question)
    language_name = LANGUAGE_NAMES[language]

    if language == "ko":
        answer_rule = (
            "답변은 반드시 한국어로 작성한다. "
            "근거 자료는 영어지만 답변은 한국어로 옮겨 설명한다. "
            "고유명사(Cadia, Horus 등)는 영어를 병기해도 좋다."
        )
    else:
        answer_rule = "Always answer in English."

    system = f"""You are the archivist of a Warhammer 40,000 lore archive.
Answer strictly from the numbered source excerpts the user provides.

Rules:
- Use ONLY the provided excerpts. Do not add lore from memory.
- If the excerpts do not answer the question, say so plainly instead of guessing.
- Cite the excerpt number after each claim, like [1] or [2].
- Never invent a citation number that is not in the excerpts.
- Be concrete and specific; avoid vague summaries.
- {answer_rule}

Response language: {language_name}"""

    context = build_context(hits)
    if context:
        user = f"Source excerpts:\n\n{context}\n\n---\n\nQuestion: {question}"
    else:
        user = f"No source excerpts were found.\n\nQuestion: {question}"

    return system, user
