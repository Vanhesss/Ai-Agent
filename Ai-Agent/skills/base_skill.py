"""
base_skill.py — Базовый класс для всех навыков (skills).
"""

from abc import ABC, abstractmethod


class BaseSkill(ABC):
    """Базовый класс навыка. Каждый навык предоставляет инструменты для агента."""

    name: str = "base"
    description: str = ""

    @abstractmethod
    def get_tool_definitions(self) -> list[dict]:
        """Вернуть список определений инструментов для Claude API."""
        ...

    @abstractmethod
    def execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Выполнить инструмент и вернуть JSON-строку."""
        ...

    def get_system_prompt_addition(self) -> str:
        """Дополнительный контекст для системного промпта (опционально)."""
        return ""
