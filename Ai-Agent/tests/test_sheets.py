"""
test_sheets.py — Тесты для sheets.py (с мок-объектами для gspread).
"""

import pytest
from unittest.mock import MagicMock, patch

import sheets


@pytest.fixture(autouse=True)
def mock_spreadsheet():
    """Мок Google Sheets для всех тестов."""
    mock_ss = MagicMock()
    sheets._spreadsheet = mock_ss
    yield mock_ss
    sheets._spreadsheet = None


def _make_worksheet(records: list[dict]) -> MagicMock:
    """Создать мок листа с данными."""
    ws = MagicMock()
    ws.get_all_records.return_value = records
    return ws


class TestCreateOrder:
    def test_creates_order_with_auto_id(self, mock_spreadsheet):
        """Заказ получает ID = max(existing) + 1."""
        existing = [{"ID": 1}, {"ID": 3}]
        ws = _make_worksheet(existing)
        mock_spreadsheet.worksheet.return_value = ws

        # Мок рецептуры для цены
        with patch.object(sheets, "get_recipe", return_value={"Цена за кг (₸)": 2500}):
            result = sheets.create_order("Арман", "Докторская", 100, "15.04.2026")

        assert result["ID"] == 4
        assert result["Клиент"] == "Арман"
        assert result["Продукт"] == "Докторская"
        assert result["Кол-во (кг)"] == 100
        assert result["Статус"] == "Новый"
        ws.append_row.assert_called_once()

    def test_creates_first_order(self, mock_spreadsheet):
        """Первый заказ получает ID = 1."""
        ws = _make_worksheet([])
        mock_spreadsheet.worksheet.return_value = ws

        with patch.object(sheets, "get_recipe", return_value=None):
            result = sheets.create_order("Тест", "Сосиски", 50, "20.04.2026")

        assert result["ID"] == 1
        assert result["Цена (₸)"] == 0  # Нет рецептуры — цена 0

    def test_uses_provided_price(self, mock_spreadsheet):
        """Если цена указана явно — используется она."""
        ws = _make_worksheet([])
        mock_spreadsheet.worksheet.return_value = ws

        result = sheets.create_order("Клиент", "Продукт", 200, "01.05.2026", price_per_kg=3000)

        assert result["Цена (₸)"] == 600000


class TestGetOrders:
    def test_returns_all_orders(self, mock_spreadsheet):
        records = [
            {"ID": 1, "Клиент": "Арман", "Статус": "Новый"},
            {"ID": 2, "Клиент": "Болат", "Статус": "Готов"},
        ]
        mock_spreadsheet.worksheet.return_value = _make_worksheet(records)

        result = sheets.get_orders()
        assert len(result) == 2

    def test_filters_by_status(self, mock_spreadsheet):
        records = [
            {"ID": 1, "Статус": "Новый"},
            {"ID": 2, "Статус": "Готов"},
            {"ID": 3, "Статус": "Новый"},
        ]
        mock_spreadsheet.worksheet.return_value = _make_worksheet(records)

        result = sheets.get_orders(status="Новый")
        assert len(result) == 2

    def test_filters_by_client(self, mock_spreadsheet):
        records = [
            {"ID": 1, "Клиент": "Арман Трейд"},
            {"ID": 2, "Клиент": "Болат Фуд"},
        ]
        mock_spreadsheet.worksheet.return_value = _make_worksheet(records)

        result = sheets.get_orders(client="арман")
        assert len(result) == 1
        assert result[0]["Клиент"] == "Арман Трейд"


class TestUpdateOrderStatus:
    def test_updates_existing_order(self, mock_spreadsheet):
        records = [{"ID": 1, "Статус": "Новый"}, {"ID": 2, "Статус": "Новый"}]
        ws = _make_worksheet(records)
        mock_spreadsheet.worksheet.return_value = ws

        result = sheets.update_order_status(2, "В работе")

        assert result is True
        ws.update_cell.assert_called_once_with(3, 7, "В работе")  # row 3, col 7

    def test_returns_false_for_missing_order(self, mock_spreadsheet):
        mock_spreadsheet.worksheet.return_value = _make_worksheet([{"ID": 1}])

        result = sheets.update_order_status(999, "Готов")
        assert result is False


class TestRecipes:
    def test_get_recipe_found(self, mock_spreadsheet):
        records = [
            {"Продукт": "Докторская", "Говядина (кг)": 25},
            {"Продукт": "Краковская", "Говядина (кг)": 30},
        ]
        mock_spreadsheet.worksheet.return_value = _make_worksheet(records)

        result = sheets.get_recipe("докторская")
        assert result["Продукт"] == "Докторская"

    def test_get_recipe_not_found(self, mock_spreadsheet):
        mock_spreadsheet.worksheet.return_value = _make_worksheet([])

        result = sheets.get_recipe("Несуществующий")
        assert result is None

    def test_get_all_recipes(self, mock_spreadsheet):
        records = [{"Продукт": "А"}, {"Продукт": "Б"}]
        mock_spreadsheet.worksheet.return_value = _make_worksheet(records)

        result = sheets.get_all_recipes()
        assert len(result) == 2


class TestCalculateMaterials:
    def test_calculates_for_single_product(self, mock_spreadsheet):
        recipe = {
            "Продукт": "Докторская",
            "Говядина (кг)": 25,
            "Свинина (кг)": 70,
            "Специи (кг)": 5,
            "Цена за кг (₸)": 2500,
        }
        mock_spreadsheet.worksheet.return_value = _make_worksheet([recipe])

        result = sheets.calculate_materials([
            {"product": "Докторская", "quantity_kg": 200},
        ])

        assert result["totals"]["Говядина (кг)"] == 50  # 25 * 2
        assert result["totals"]["Свинина (кг)"] == 140  # 70 * 2
        assert result["totals"]["Специи (кг)"] == 10  # 5 * 2
        assert "Цена за кг (₸)" not in result["totals"]

    def test_handles_missing_recipe(self, mock_spreadsheet):
        mock_spreadsheet.worksheet.return_value = _make_worksheet([])

        result = sheets.calculate_materials([
            {"product": "Неизвестный", "quantity_kg": 100},
        ])

        assert result["details"][0]["error"] == "Рецептура не найдена"
        assert result["totals"] == {}


class TestClients:
    def test_get_client_found(self, mock_spreadsheet):
        records = [{"Название": "Арман Трейд", "Телефон": "+7777"}]
        mock_spreadsheet.worksheet.return_value = _make_worksheet(records)

        result = sheets.get_client("арман")
        assert result["Название"] == "Арман Трейд"

    def test_get_client_not_found(self, mock_spreadsheet):
        mock_spreadsheet.worksheet.return_value = _make_worksheet([])

        result = sheets.get_client("Неизвестный")
        assert result is None

    def test_get_all_clients(self, mock_spreadsheet):
        records = [{"Название": "А"}, {"Название": "Б"}]
        mock_spreadsheet.worksheet.return_value = _make_worksheet(records)

        result = sheets.get_all_clients()
        assert len(result) == 2
