"""Зависимости FastAPI для обработчиков запросов."""

from typing import Annotated

from fastapi import Depends

from src.context import get_trace_id

TraceId = Annotated[str | None, Depends(get_trace_id)]
