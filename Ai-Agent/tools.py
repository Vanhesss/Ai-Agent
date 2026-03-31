"""
tools.py — Определения инструментов для Claude API и диспетчер выполнения.
"""

import json
import logging

import sheets

logger = logging.getLogger(__name__)

# ─── Определения инструментов (JSON Schema для Claude API) ────────────────────

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "create_order",
        "description": (
            "Создать новый заказ. Используй когда клиент хочет заказать продукцию. "
            "Примеры: 'Создай заказ на 100 кг Докторской для Арман на 15.04.2026'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client": {
                    "type": "string",
                    "description": "Название клиента",
                },
                "product": {
                    "type": "string",
                    "description": "Название продукта (например: Докторская, Краковская)",
                },
                "quantity_kg": {
                    "type": "number",
                    "description": "Количество в килограммах",
                },
                "delivery_date": {
                    "type": "string",
                    "description": "Дата отгрузки в формате ДД.ММ.ГГГГ",
                },
                "price_per_kg": {
                    "type": "number",
                    "description": "Цена за кг в тенге (₸). Если не указана — берётся из рецептуры.",
                },
            },
            "required": ["client", "product", "quantity_kg", "delivery_date"],
        },
    },
    {
        "name": "get_orders",
        "description": (
            "Получить список заказов. Можно фильтровать по статусу, клиенту, дате. "
            "Примеры: 'Покажи все новые заказы', 'Заказы Арман', 'Что на 15 апреля?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Фильтр по статусу: Новый, В работе, Готов, Отгружен",
                },
                "client": {
                    "type": "string",
                    "description": "Фильтр по имени клиента",
                },
                "date": {
                    "type": "string",
                    "description": "Фильтр по дате отгрузки (ДД.ММ.ГГГГ)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "update_order_status",
        "description": (
            "Обновить статус заказа по ID. "
            "Примеры: 'Заказ #5 готов', 'Переведи заказ 3 в работу'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "integer",
                    "description": "ID заказа",
                },
                "new_status": {
                    "type": "string",
                    "description": "Новый статус: Новый, В работе, Готов, Отгружен, Отменён",
                },
            },
            "required": ["order_id", "new_status"],
        },
    },
    {
        "name": "get_recipe",
        "description": (
            "Получить рецептуру конкретного продукта. "
            "Примеры: 'Рецепт Докторской', 'Что входит в Краковскую?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "Название продукта",
                },
            },
            "required": ["product_name"],
        },
    },
    {
        "name": "get_all_recipes",
        "description": (
            "Получить все рецептуры. "
            "Примеры: 'Покажи все рецепты', 'Какие продукты мы делаем?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "calculate_materials",
        "description": (
            "Рассчитать необходимое сырьё для производства. Рецептуры на 100 кг. "
            "Примеры: 'Сколько сырья на 200 кг Докторской и 150 кг Краковской?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "products": {
                    "type": "array",
                    "description": "Список продуктов с количеством",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product": {
                                "type": "string",
                                "description": "Название продукта",
                            },
                            "quantity_kg": {
                                "type": "number",
                                "description": "Количество в кг",
                            },
                        },
                        "required": ["product", "quantity_kg"],
                    },
                },
            },
            "required": ["products"],
        },
    },
    {
        "name": "get_client",
        "description": (
            "Найти клиента по имени. "
            "Примеры: 'Найди клиента Арман', 'Контакты Алматы Фуд'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Название или часть названия клиента",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_all_clients",
        "description": (
            "Получить список всех клиентов. "
            "Примеры: 'Покажи всех клиентов', 'Список клиентов'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


# ─── Диспетчер выполнения инструментов ────────────────────────────────────────


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Выполнить инструмент и вернуть результат как JSON-строку."""
    try:
        if tool_name == "create_order":
            result = sheets.create_order(
                client=tool_input["client"],
                product=tool_input["product"],
                quantity_kg=tool_input["quantity_kg"],
                delivery_date=tool_input["delivery_date"],
                price_per_kg=tool_input.get("price_per_kg"),
            )
        elif tool_name == "get_orders":
            result = sheets.get_orders(
                status=tool_input.get("status"),
                client=tool_input.get("client"),
                date=tool_input.get("date"),
            )
        elif tool_name == "update_order_status":
            success = sheets.update_order_status(
                order_id=tool_input["order_id"],
                new_status=tool_input["new_status"],
            )
            result = {
                "success": success,
                "order_id": tool_input["order_id"],
                "new_status": tool_input["new_status"],
            }
        elif tool_name == "get_recipe":
            recipe = sheets.get_recipe(tool_input["product_name"])
            result = recipe if recipe else {"error": "Рецептура не найдена"}
        elif tool_name == "get_all_recipes":
            result = sheets.get_all_recipes()
        elif tool_name == "calculate_materials":
            result = sheets.calculate_materials(tool_input["products"])
        elif tool_name == "get_client":
            client = sheets.get_client(tool_input["name"])
            result = client if client else {"error": "Клиент не найден"}
        elif tool_name == "get_all_clients":
            result = sheets.get_all_clients()
        else:
            result = {"error": f"Неизвестный инструмент: {tool_name}"}

    except Exception as e:
        logger.error(f"Ошибка при выполнении {tool_name}: {e}")
        result = {"error": f"Ошибка выполнения: {str(e)}"}

    return json.dumps(result, ensure_ascii=False)
