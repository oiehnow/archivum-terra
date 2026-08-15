"""LLM 프로바이더.

교체 가능한 슬롯으로 둔다. 새 프로바이더는 LLMProvider 프로토콜만 구현하면 되고
검색·웹 코드는 손대지 않는다. OpenAI 가 공식 구독 OAuth 를 내놓거나 다른 모델로
옮길 때 이 파일에 구현체 하나를 추가하면 끝난다.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Protocol


class LLMProvider(Protocol):
    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        """답변 토큰을 순서대로 흘려보낸다."""
        ...


class GeminiProvider:
    """Gemini Flash. 무료 티어 1,500 요청/일 안에서 운영한다."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-flash-latest")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY 가 설정되지 않았습니다")
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        from google.genai import types

        client = self._get_client()
        response = await client.aio.models.generate_content_stream(
            model=self.model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.2,  # 로어 질의는 창의성보다 근거 충실도가 중요하다
                max_output_tokens=1600,
            ),
        )
        async for chunk in response:
            if chunk.text:
                yield chunk.text


class EchoProvider:
    """프로바이더 미설정 시 쓰는 안내용 대체 구현."""

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        yield "LLM 프로바이더가 설정되지 않았습니다. 관리자가 GEMINI_API_KEY 를 등록해야 합니다."


def get_provider() -> LLMProvider:
    if os.getenv("GEMINI_API_KEY"):
        return GeminiProvider()
    return EchoProvider()
