"""Проверка работы HTTP-сервиса без внешних обращений."""

from fastapi import APIRouter

from src.api.dependencies import TraceId

router = APIRouter()


@router.get("/health")
async def health(_trace_id: TraceId) -> dict[str, str]:
    """Вернуть состояние процесса без проверки БД."""
    return {"status": "ok"}
