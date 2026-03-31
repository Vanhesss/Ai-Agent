"""
base_agent.py — Базовый класс с общей логикой агентного цикла.
"""

import json
import logging
from abc import ABC, abstractmethod

import anthropic

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Базовый класс агента. Содержит агентный цикл."""

    name: str = "base"
    model: str = "claude-haiku-4-5-20251001"
    system_prompt: str = ""
    max_iterations: int = 10

    def __init__(self, claude_client: anthropic.Anthropic) -> None:
        self.claude = claude_client

    @abstractmethod
    def get_tools(self) -> list[dict]:
        """Вернуть список инструментов агента."""
        ...

    @abstractmethod
    def execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Выполнить инструмент и вернуть JSON-строку."""
        ...

    async def run(self, messages: list[dict]) -> str:
        """Запустить агентный цикл. Возвращает текстовый ответ."""
        tools = self.get_tools()

        for iteration in range(self.max_iterations):
            logger.info(f"🔄 [{self.name}] Итерация {iteration + 1}")

            response = self.claude.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt,
                tools=tools,
                messages=messages,
            )

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        logger.info(f"🔧 [{self.name}] {block.name}({block.input})")
                        result = self.execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                messages.append({"role": "user", "content": tool_results})
                continue

            elif response.stop_reason == "end_turn":
                text = "".join(
                    block.text for block in response.content
                    if hasattr(block, "text")
                )
                return text

        return "Запрос слишком сложный. Попробуй разбить на части."
