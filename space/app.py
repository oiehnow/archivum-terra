"""Archivum Terra — Warhammer 40k 로어 RAG 서비스.

방문자는 간편 로그인만 하면 바로 쓴다. 추론 비용은 운영자가 Gemini 무료 티어로 부담하고,
계정당 하루 20질문으로 남용을 막는다.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from space import quota  # noqa: E402
from space.auth import current_user, register_auth_routes  # noqa: E402
from space.llm import get_provider  # noqa: E402
from space.search import search  # noqa: E402
from wh40k.prompt import build_messages  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
AUTH_DISABLED = os.getenv("AUTH_DISABLED") == "1"

app = FastAPI(title="Archivum Terra", docs_url=None, redoc_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "dev-only-not-for-production"),
    same_site="lax",
    https_only=os.getenv("HTTPS_ONLY") == "1",
)

register_auth_routes(app)

_provider = None


def provider():
    global _provider
    if _provider is None:
        _provider = get_provider()
    return _provider


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/config")
async def config():
    """프론트가 어떤 LLM 경로를 쓸지 결정하는 데 필요한 정보."""
    return JSONResponse({
        "llm_mode": "server" if os.getenv("GEMINI_API_KEY") else "puter",
        "puter_model": os.getenv("PUTER_MODEL", "gpt-5-nano"),
    })


@app.get("/api/me")
async def me(request: Request):
    user = current_user(request)
    if not user:
        return JSONResponse({"authenticated": False})
    return JSONResponse({
        "authenticated": True,
        "name": user.get("name"),
        "email": user.get("email"),
        "remaining": quota.remaining(user["sub"]),
        "quota": quota.DAILY_QUOTA,
    })


def _validate_question(body: dict) -> str:
    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="질문이 비어 있습니다")
    if len(question) > 500:
        raise HTTPException(status_code=400, detail="질문이 너무 깁니다 (500자 이내)")
    return question


@app.post("/api/retrieve")
async def retrieve(request: Request):
    """검색만 수행하고 근거와 프롬프트를 돌려준다.

    답변 생성은 브라우저가 Puter 로 직접 한다. 서버는 LLM 키를 갖지 않으므로
    운영자가 발급할 것도, 부담할 비용도 없다.
    """
    question = _validate_question(await request.json())

    try:
        hits = search(question)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"기록보관소를 열지 못했습니다: {exc}")

    if not hits:
        return JSONResponse({"hits": [], "sources": [], "system": "", "user": ""})

    system, user_message = build_messages(question, hits)
    return JSONResponse({
        "system": system,
        "user": user_message,
        "sources": [
            {
                "n": i,
                "title": hit["title"],
                "section": hit["section"],
                "url": hit["source_url"] or "",
            }
            for i, hit in enumerate(hits, start=1)
        ],
    })


@app.post("/api/ask")
async def ask(request: Request):
    """서버 측 LLM 경로 (운영자가 GEMINI_API_KEY 를 넣었을 때만 쓴다)."""
    user = current_user(request)
    if not user and not AUTH_DISABLED:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")

    question = _validate_question(await request.json())

    sub = user["sub"] if user else "anonymous"
    left = quota.consume(sub)
    if left < 0:
        hours = quota.seconds_until_reset() // 3600
        raise HTTPException(
            status_code=429,
            detail=f"오늘 질문 한도를 모두 썼습니다. 약 {hours}시간 뒤 초기화됩니다.",
        )

    return StreamingResponse(
        _stream_answer(question, left),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_answer(question: str, remaining_after: int):
    def event(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    try:
        hits = search(question)
    except Exception as exc:  # 인덱스 로드 실패 등
        yield event({"error": f"기록보관소를 열지 못했습니다: {exc}"})
        return

    if not hits:
        yield event({"token": "해당 질문에 대한 기록을 찾지 못했습니다."})
        yield event({"done": True, "remaining": remaining_after})
        return

    system, user_message = build_messages(question, hits)

    try:
        async for token in provider().stream(system, user_message):
            yield event({"token": token})
    except Exception as exc:
        yield event({"error": f"응답 생성에 실패했습니다: {exc}"})
        return

    yield event({
        "sources": [
            {
                "n": i,
                "title": hit["title"],
                "section": hit["section"],
                "url": hit["source_url"] or "",
            }
            for i, hit in enumerate(hits, start=1)
        ]
    })
    yield event({"done": True, "remaining": remaining_after})


@app.get("/healthz")
async def healthz():
    return {"ok": True}


app.mount("/", StaticFiles(directory=str(STATIC), html=True), name="static")
