"""
validators.py — Валидация входных данных.
"""

import re
from datetime import datetime
from typing import Optional


def parse_date(text: str) -> Optional[str]:
    """Распознать дату из текста и вернуть в формате ДД.ММ.ГГГГ."""
    # Формат ДД.ММ.ГГГГ
    match = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text.strip())
    if match:
        try:
            day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            datetime(year, month, day)
            return f"{day:02d}.{month:02d}.{year}"
        except ValueError:
            return None

    return None


def validate_quantity(value) -> Optional[float]:
    """Проверить что количество — положительное число."""
    try:
        qty = float(value)
        if qty > 0:
            return qty
    except (ValueError, TypeError):
        pass
    return None
