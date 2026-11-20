"""Проверка работы HTTP-сервиса без внешних обращений."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Вернуть состояние процесса без проверки БД."""
    return {"status": "ok"}
