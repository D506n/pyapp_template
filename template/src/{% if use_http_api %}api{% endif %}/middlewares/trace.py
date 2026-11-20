"""Изоляция входного X-Trace-ID в контексте запроса."""

from starlette.types import ASGIApp, Receive, Scope, Send

from src.context import _trace_id


class TraceIDMiddleware:
    """Изолировать X-Trace-ID запроса, включая смонтированные приложения."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        trace_id = None
        for name, value in scope["headers"]:
            if name.lower() == b"x-trace-id":
                trace_id = value.decode("latin-1")
                break
        token = _trace_id.set(trace_id)
        try:
            await self.app(scope, receive, send)
        finally:
            _trace_id.reset(token)
