"""간편 로그인 (OIDC).

방문자는 클릭 한 번으로 로그인하고 바로 질문한다. API 키 발급 같은 준비는 없다.

제공자는 설정으로 바꾼다. Google 이 기본이고, Sign in with ChatGPT 클라이언트 등록이
승인되면 환경변수만 바꾸면 된다 — 둘 다 표준 OIDC 라 코드는 그대로다.
"""

from __future__ import annotations

import os

from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

PROVIDER = os.getenv("OIDC_PROVIDER", "google")

_METADATA = {
    "google": "https://accounts.google.com/.well-known/openid-configuration",
    "chatgpt": os.getenv("CHATGPT_OIDC_METADATA", ""),
}

oauth = OAuth()

_client_id = os.getenv("OIDC_CLIENT_ID") or os.getenv("GOOGLE_CLIENT_ID")
_client_secret = os.getenv("OIDC_CLIENT_SECRET") or os.getenv("GOOGLE_CLIENT_SECRET")

if _client_id and _client_secret:
    oauth.register(
        name="sso",
        server_metadata_url=_METADATA.get(PROVIDER) or _METADATA["google"],
        client_id=_client_id,
        client_secret=_client_secret,
        client_kwargs={"scope": "openid email profile"},
    )


def auth_configured() -> bool:
    return bool(_client_id and _client_secret)


def current_user(request: Request) -> dict | None:
    return request.session.get("user")


def register_auth_routes(app: FastAPI) -> None:
    @app.get("/auth/login")
    async def login(request: Request):
        if not auth_configured():
            return RedirectResponse("/?auth=unconfigured")
        redirect_uri = os.getenv("OAUTH_REDIRECT_URI") or str(request.url_for("auth_callback"))
        return await oauth.sso.authorize_redirect(request, redirect_uri)

    @app.get("/auth/callback", name="auth_callback")
    async def auth_callback(request: Request):
        from space import quota

        try:
            token = await oauth.sso.authorize_access_token(request)
        except Exception:
            return RedirectResponse("/?auth=failed")

        claims = token.get("userinfo") or {}
        sub = claims.get("sub")
        if not sub:
            return RedirectResponse("/?auth=failed")

        request.session["user"] = {
            "sub": sub,
            "email": claims.get("email"),
            "name": claims.get("name") or claims.get("given_name"),
            "picture": claims.get("picture"),
        }
        quota.ensure_user(sub, claims.get("email"), claims.get("name"))
        return RedirectResponse("/")

    @app.get("/auth/logout")
    async def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/")
