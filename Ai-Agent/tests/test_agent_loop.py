"""
test_agent_loop.py — Тесты для агентного цикла в bot.py.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from bot import agent_loop, user_histories, _trim_history, _check_access


class TestCheckAccess:
    @patch("bot.ALLOWED_USERS", [])
    def test_empty_list_allows_all(self):
        assert _check_access(12345) is True

    @patch("bot.ALLOWED_USERS", [111, 222])
    def test_allowed_user(self):
        assert _check_access(111) is True

    @patch("bot.ALLOWED_USERS", [111, 222])
    def test_denied_user(self):
        assert _check_access(999) is False


class TestTrimHistory:
    def test_no_trim_needed(self):
        history = [{"role": "user", "content": "hi"}] * 10
        result = _trim_history(history)
        assert len(result) == 10

    @patch("bot.MAX_HISTORY", 5)
    def test_trims_to_max(self):
        history = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        result = _trim_history(history)
        assert len(result) == 5
        assert result[0]["content"] == "msg5"  # Сохраняются последние


class TestAgentLoop:
    @pytest.fixture(autouse=True)
    def clear_histories(self):
        user_histories.clear()
        yield
        user_histories.clear()

    @pytest.mark.asyncio
    @patch("bot.claude")
    async def test_end_turn_returns_text(self, mock_claude):
        """Простой ответ без вызовов инструментов."""
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Привет! Чем могу помочь?"

        response = MagicMock()
        response.stop_reason = "end_turn"
        response.content = [text_block]

        mock_claude.messages.create.return_value = response

        result = await agent_loop("Привет", user_id=100)

        assert result == "Привет! Чем могу помочь?"
        assert len(user_histories[100]) == 2  # user + assistant

    @pytest.mark.asyncio
    @patch("bot.execute_tool")
    @patch("bot.claude")
    async def test_tool_use_then_end_turn(self, mock_claude, mock_execute):
        """Один вызов инструмента, затем финальный ответ."""
        # Первый ответ: tool_use
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "get_all_recipes"
        tool_block.input = {}
        tool_block.id = "tool_123"

        response1 = MagicMock()
        response1.stop_reason = "tool_use"
        response1.content = [tool_block]

        # Второй ответ: end_turn
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Вот рецепты!"

        response2 = MagicMock()
        response2.stop_reason = "end_turn"
        response2.content = [text_block]

        mock_claude.messages.create.side_effect = [response1, response2]
        mock_execute.return_value = '[{"Продукт": "Докторская"}]'

        result = await agent_loop("Покажи рецепты", user_id=200)

        assert result == "Вот рецепты!"
        assert mock_claude.messages.create.call_count == 2
        mock_execute.assert_called_once_with("get_all_recipes", {})

    @pytest.mark.asyncio
    @patch("bot.claude")
    async def test_max_iterations_returns_fallback(self, mock_claude):
        """При превышении лимита итераций — возвращает fallback."""
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "get_orders"
        tool_block.input = {}
        tool_block.id = "tool_loop"

        response = MagicMock()
        response.stop_reason = "tool_use"
        response.content = [tool_block]

        # Всегда возвращает tool_use — бесконечный цикл
        mock_claude.messages.create.return_value = response

        with patch("bot.execute_tool", return_value='[]'):
            with patch("bot.MAX_ITERATIONS", 3):
                result = await agent_loop("Тест", user_id=300)

        assert "сложный" in result
