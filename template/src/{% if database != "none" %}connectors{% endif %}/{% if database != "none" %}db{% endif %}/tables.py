"""Пустые метаданные; предметные модели добавляются явно."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """База будущих моделей приложения."""
