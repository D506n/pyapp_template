"""Bearer-аутентификация API и смонтированных приложений."""

from secrets import compare_digest

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from src.env import Settings

PUBLIC_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"})


class BearerAuthMiddleware:
    """Проверить один Authorization: Bearer, оставив документацию публичной."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._token = Settings().api_token.encode("utf-8")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "http" and scope["path"] in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return
        headers = [value for name, value in scope["headers"] if name.lower() == b"authorization"]
        authorized = False
        if len(headers) == 1:
            scheme, separator, credentials = headers[0].partition(b" ")
            if (
                scheme.lower() == b"bearer"
                and separator
                and credentials
                and not any(byte <= 32 or byte >= 127 for byte in credentials)
            ):
                authorized = compare_digest(credentials, self._token)
        if not authorized:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                response = JSONResponse(
                    {"detail": "Unauthorized"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
