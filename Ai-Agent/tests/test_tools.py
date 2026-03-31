"""
test_tools.py — Тесты для tools.py: определения инструментов и диспетчер.
"""

import json
import pytest
from unittest.mock import patch

from tools import TOOL_DEFINITIONS, execute_tool


class TestToolDefinitions:
    def test_all_tools_have_required_fields(self):
        """Каждый инструмент содержит name, description, input_schema."""
        for tool in TOOL_DEFINITIONS:
            assert "name" in tool, f"Отсутствует name: {tool}"
            assert "description" in tool, f"Отсутствует description: {tool.get('name')}"
            assert "input_schema" in tool, f"Отсутствует input_schema: {tool.get('name')}"

    def test_expected_tool_count(self):
        """Должно быть 8 инструментов."""
        assert len(TOOL_DEFINITIONS) == 8

    def test_tool_names_are_unique(self):
        """Имена инструментов уникальны."""
        names = [t["name"] for t in TOOL_DEFINITIONS]
        assert len(names) == len(set(names))

    def test_expected_tools_present(self):
        """Все ожидаемые инструменты на месте."""
        names = {t["name"] for t in TOOL_DEFINITIONS}
        expected = {
            "create_order", "get_orders", "update_order_status",
            "get_recipe", "get_all_recipes", "calculate_materials",
            "get_client", "get_all_clients",
        }
        assert names == expected

    def test_schemas_have_type_object(self):
        """Все input_schema имеют type: object."""
        for tool in TOOL_DEFINITIONS:
            assert tool["input_schema"]["type"] == "object", tool["name"]


class TestExecuteTool:
    @patch("tools.sheets")
    def test_create_order(self, mock_sheets):
        mock_sheets.create_order.return_value = {"ID": 1, "Клиент": "Тест"}

        result = json.loads(execute_tool("create_order", {
            "client": "Тест",
            "product": "Докторская",
            "quantity_kg": 100,
            "delivery_date": "15.04.2026",
        }))

        assert result["ID"] == 1
        mock_sheets.create_order.assert_called_once()

    @patch("tools.sheets")
    def test_get_orders(self, mock_sheets):
        mock_sheets.get_orders.return_value = [{"ID": 1}, {"ID": 2}]

        result = json.loads(execute_tool("get_orders", {"status": "Новый"}))

        assert len(result) == 2
        mock_sheets.get_orders.assert_called_once_with(status="Новый", client=None, date=None)

    @patch("tools.sheets")
    def test_update_order_status(self, mock_sheets):
        mock_sheets.update_order_status.return_value = True

        result = json.loads(execute_tool("update_order_status", {
            "order_id": 1,
            "new_status": "Готов",
        }))

        assert result["success"] is True

    @patch("tools.sheets")
    def test_get_recipe(self, mock_sheets):
        mock_sheets.get_recipe.return_value = {"Продукт": "Докторская"}

        result = json.loads(execute_tool("get_recipe", {"product_name": "Докторская"}))

        assert result["Продукт"] == "Докторская"

    @patch("tools.sheets")
    def test_get_recipe_not_found(self, mock_sheets):
        mock_sheets.get_recipe.return_value = None

        result = json.loads(execute_tool("get_recipe", {"product_name": "Нет"}))

        assert "error" in result

    @patch("tools.sheets")
    def test_unknown_tool(self, mock_sheets):
        result = json.loads(execute_tool("nonexistent_tool", {}))

        assert "error" in result

    @patch("tools.sheets")
    def test_handles_exception(self, mock_sheets):
        mock_sheets.get_all_clients.side_effect = Exception("API error")

        result = json.loads(execute_tool("get_all_clients", {}))

        assert "error" in result
        assert "API error" in result["error"]
