"""
sheets.py — Модуль для работы с Google Sheets.

Этот файл содержит все функции для чтения и записи данных
в Google-таблицу. Библиотека gspread делает это просто.

Структура таблицы:
- Лист "Заказы":    ID | Дата | Клиент | Продукт | Кол-во (кг) | Цена (₸) | Статус | Дата отгрузки
- Лист "Рецептуры": Продукт | Говядина (кг) | Свинина (кг) | Шпик (кг) | Специи (кг) | Оболочка (м) | Цена за кг (₸)
- Лист "Клиенты":   Название | Контакт | Телефон | Адрес | Скидка %
"""

import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from config import SHEET_ORDERS, SHEET_RECIPES, SHEET_CLIENTS

# ============================================================
# ПОДКЛЮЧЕНИЕ К GOOGLE SHEETS
# ============================================================
# Область доступа — что наш бот может делать с Google
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",       # Читать/писать таблицы
    "https://www.googleapis.com/auth/drive.readonly",      # Видеть файлы на диске
]


def connect_sheets(credentials_file: str, spreadsheet_id: str):
    """
    Подключается к Google-таблице.

    credentials_file — путь к JSON-файлу сервисного аккаунта
    spreadsheet_id — ID таблицы (из URL: docs.google.com/spreadsheets/d/ЭТОТ_ID/edit)
    """
    creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(spreadsheet_id)
    return spreadsheet


# ============================================================
# ГЛОБАЛЬНАЯ ПЕРЕМЕННАЯ — подключение к таблице
# ============================================================
# Инициализируется при запуске бота (в bot.py)
_spreadsheet = None


def init(credentials_file: str, spreadsheet_id: str):
    """Инициализация подключения. Вызывается один раз при старте бота."""
    global _spreadsheet
    _spreadsheet = connect_sheets(credentials_file, spreadsheet_id)
    print(f"✅ Подключено к Google Sheets: {_spreadsheet.title}")


def _get_sheet(name: str):
    """Получает лист по названию."""
    if _spreadsheet is None:
        raise RuntimeError("Google Sheets не инициализирован! Вызови sheets.init() сначала.")
    return _spreadsheet.worksheet(name)


# ============================================================
# ЗАКАЗЫ
# ============================================================

def create_order(client: str, product: str, quantity_kg: float,
                 delivery_date: str, price_per_kg: float = None) -> dict:
    """
    Создаёт новый заказ в таблице.

    Возвращает словарь с данными заказа.
    Если price_per_kg не указана — берёт из рецептур.
    """
    sheet = _get_sheet(SHEET_ORDERS)

    # Если цена не указана — ищем в рецептурах
    if price_per_kg is None:
        recipe = get_recipe(product)
        if recipe and "price_per_kg" in recipe:
            price_per_kg = float(recipe["price_per_kg"])
        else:
            price_per_kg = 0  # Цена неизвестна

    total_price = round(quantity_kg * price_per_kg, 2)

    # Генерируем ID заказа (простой счётчик)
    all_rows = sheet.get_all_values()
    order_id = len(all_rows)  # Первая строка — заголовок, так что ID = количество строк

    # Новая строка для таблицы
    new_row = [
        order_id,                                    # ID
        datetime.now().strftime("%d.%m.%Y %H:%M"),   # Дата создания
        client,                                       # Клиент
        product,                                      # Продукт
        quantity_kg,                                   # Кол-во (кг)
        total_price,                                   # Цена (₸)
        "Новый",                                       # Статус
        delivery_date,                                 # Дата отгрузки
    ]

    sheet.append_row(new_row, value_input_option="USER_ENTERED")

    return {
        "order_id": order_id,
        "client": client,
        "product": product,
        "quantity_kg": quantity_kg,
        "price_per_kg": price_per_kg,
        "total_price": total_price,
        "delivery_date": delivery_date,
        "status": "Новый",
    }


def get_orders(status: str = None, client: str = None,
               date: str = None) -> list[dict]:
    """
    Получает заказы с возможностью фильтрации.

    status — фильтр по статусу ("Новый", "В работе", "Готов", "Отгружен")
    client — фильтр по клиенту
    date — фильтр по дате отгрузки
    """
    sheet = _get_sheet(SHEET_ORDERS)
    rows = sheet.get_all_records()

    # Применяем фильтры
    if status:
        rows = [r for r in rows if r.get("Статус", "").lower() == status.lower()]
    if client:
        rows = [r for r in rows if client.lower() in r.get("Клиент", "").lower()]
    if date:
        rows = [r for r in rows if date in r.get("Дата отгрузки", "")]

    return rows


def update_order_status(order_id: int, new_status: str) -> bool:
    """Обновляет статус заказа по ID."""
    sheet = _get_sheet(SHEET_ORDERS)
    all_rows = sheet.get_all_values()

    for i, row in enumerate(all_rows):
        if i == 0:  # Пропускаем заголовок
            continue
        if str(row[0]) == str(order_id):
            # Столбец "Статус" — 7-й (индекс 6, в Sheets нумерация с 1 → col=7)
            sheet.update_cell(i + 1, 7, new_status)
            return True

    return False


# ============================================================
# РЕЦЕПТУРЫ
# ============================================================

def get_recipe(product_name: str) -> dict | None:
    """
    Получает рецептуру продукта.

    Ищет по названию (частичное совпадение, без учёта регистра).
    Возвращает словарь или None если не найдено.
    """
    sheet = _get_sheet(SHEET_RECIPES)
    rows = sheet.get_all_records()

    for row in rows:
        product = row.get("Продукт", "")
        if product_name.lower() in product.lower() or product.lower() in product_name.lower():
            return {
                "product": product,
                "beef_kg": row.get("Говядина (кг)", 0),
                "pork_kg": row.get("Свинина (кг)", 0),
                "fat_kg": row.get("Шпик (кг)", 0),
                "spices_kg": row.get("Специи (кг)", 0),
                "casing_m": row.get("Оболочка (м)", 0),
                "price_per_kg": row.get("Цена за кг (₸)", 0),
            }

    return None


def get_all_recipes() -> list[dict]:
    """Получает все рецептуры."""
    sheet = _get_sheet(SHEET_RECIPES)
    return sheet.get_all_records()


def calculate_materials(products: list[dict]) -> dict:
    """
    Рассчитывает необходимое сырьё для списка продуктов.

    products — список словарей: [{"product": "Докторская", "quantity_kg": 50}, ...]

    Возвращает общее количество каждого вида сырья.
    Рецептуры указаны на 100 кг готовой продукции.
    """
    totals = {
        "beef_kg": 0,
        "pork_kg": 0,
        "fat_kg": 0,
        "spices_kg": 0,
        "casing_m": 0,
    }

    details = []  # Детализация по каждому продукту

    for item in products:
        recipe = get_recipe(item["product"])
        if recipe is None:
            details.append({
                "product": item["product"],
                "error": "Рецептура не найдена"
            })
            continue

        # Рецептура указана на 100 кг, пересчитываем на нужное количество
        factor = item["quantity_kg"] / 100.0

        product_materials = {
            "product": item["product"],
            "quantity_kg": item["quantity_kg"],
            "beef_kg": round(float(recipe["beef_kg"]) * factor, 2),
            "pork_kg": round(float(recipe["pork_kg"]) * factor, 2),
            "fat_kg": round(float(recipe["fat_kg"]) * factor, 2),
            "spices_kg": round(float(recipe["spices_kg"]) * factor, 2),
            "casing_m": round(float(recipe["casing_m"]) * factor, 2),
        }

        details.append(product_materials)

        # Добавляем в общий итог
        for key in totals:
            totals[key] += product_materials[key]

    # Округляем итоги
    for key in totals:
        totals[key] = round(totals[key], 2)

    return {"totals": totals, "details": details}


# ============================================================
# КЛИЕНТЫ
# ============================================================

def get_client(name: str) -> dict | None:
    """Ищет клиента по названию (частичное совпадение)."""
    sheet = _get_sheet(SHEET_CLIENTS)
    rows = sheet.get_all_records()

    for row in rows:
        client_name = row.get("Название", "")
        if name.lower() in client_name.lower() or client_name.lower() in name.lower():
            return row

    return None


def get_all_clients() -> list[dict]:
    """Получает список всех клиентов."""
    sheet = _get_sheet(SHEET_CLIENTS)
    return sheet.get_all_records()


# ============================================================
# АНАЛИТИКА (работает без Claude API — 0 токенов!)
# ============================================================

def get_today_orders() -> dict:
    """
    Все заказы на сегодня + итоги.
    Ищет по дате отгрузки = сегодня, а также незавершённые заказы.
    """
    sheet = _get_sheet(SHEET_ORDERS)
    rows = sheet.get_all_records()

    today = datetime.now().strftime("%d.%m.%Y")
    today_orders = []
    total_kg = 0
    total_price = 0

    for r in rows:
        delivery = str(r.get("Дата отгрузки", ""))
        status = str(r.get("Статус", ""))

        # Заказы на сегодня ИЛИ незавершённые (Новый, В работе)
        is_today = today in delivery
        is_active = status in ("Новый", "В работе")

        if is_today or is_active:
            today_orders.append(r)
            try:
                total_kg += float(r.get("Кол-во (кг)", 0))
                total_price += float(r.get("Цена (₸)", 0))
            except (ValueError, TypeError):
                pass

    return {
        "date": today,
        "orders": today_orders,
        "total_kg": round(total_kg, 1),
        "total_price": round(total_price, 2),
        "count": len(today_orders),
    }


def get_purchase_list() -> dict:
    """
    Считает сколько сырья нужно закупить для всех новых заказов.
    Работает без Claude — чистый Python.
    """
    sheet = _get_sheet(SHEET_ORDERS)
    rows = sheet.get_all_records()

    # Собираем все заказы со статусом "Новый"
    new_orders = [r for r in rows if str(r.get("Статус", "")) == "Новый"]

    if not new_orders:
        return {"orders_count": 0, "totals": {}, "details": []}

    # Группируем по продукту и суммируем кг
    products = {}
    for order in new_orders:
        product = order.get("Продукт", "")
        try:
            kg = float(order.get("Кол-во (кг)", 0))
        except (ValueError, TypeError):
            kg = 0
        products[product] = products.get(product, 0) + kg

    # Считаем сырьё через рецептуры
    product_list = [{"product": p, "quantity_kg": q} for p, q in products.items()]
    materials = calculate_materials(product_list)

    return {
        "orders_count": len(new_orders),
        "products": products,
        "totals": materials["totals"],
        "details": materials["details"],
    }


def get_weekly_stats() -> dict:
    """
    Статистика за последние 7 дней: выручка, кол-во заказов,
    топ продуктов, топ клиентов.
    """
    sheet = _get_sheet(SHEET_ORDERS)
    rows = sheet.get_all_records()

    # Определяем даты за последние 7 дней
    from datetime import timedelta
    today = datetime.now()
    week_dates = set()
    for i in range(7):
        d = today - timedelta(days=i)
        week_dates.add(d.strftime("%d.%m.%Y"))

    # Фильтруем заказы за неделю (по дате создания)
    week_orders = []
    for r in rows:
        order_date = str(r.get("Дата", ""))
        # Берём только дату (без времени)
        date_part = order_date.split(" ")[0] if " " in order_date else order_date
        if date_part in week_dates:
            week_orders.append(r)

    if not week_orders:
        return {
            "period": f"{(today - timedelta(days=6)).strftime('%d.%m')} — {today.strftime('%d.%m.%Y')}",
            "total_orders": 0,
            "total_revenue": 0,
            "total_kg": 0,
            "top_products": [],
            "top_clients": [],
        }

    # Считаем итоги
    total_revenue = 0
    total_kg = 0
    products_kg = {}
    clients_revenue = {}

    for r in week_orders:
        try:
            price = float(r.get("Цена (₸)", 0))
            kg = float(r.get("Кол-во (кг)", 0))
        except (ValueError, TypeError):
            price = 0
            kg = 0

        total_revenue += price
        total_kg += kg

        product = r.get("Продукт", "Неизвестно")
        products_kg[product] = products_kg.get(product, 0) + kg

        client = r.get("Клиент", "Неизвестно")
        clients_revenue[client] = clients_revenue.get(client, 0) + price

    # Топ-3 продуктов по кг
    top_products = sorted(products_kg.items(), key=lambda x: x[1], reverse=True)[:3]

    # Топ-3 клиентов по выручке
    top_clients = sorted(clients_revenue.items(), key=lambda x: x[1], reverse=True)[:3]

    return {
        "period": f"{(today - timedelta(days=6)).strftime('%d.%m')} — {today.strftime('%d.%m.%Y')}",
        "total_orders": len(week_orders),
        "total_revenue": round(total_revenue, 2),
        "total_kg": round(total_kg, 1),
        "top_products": top_products,
        "top_clients": top_clients,
    }