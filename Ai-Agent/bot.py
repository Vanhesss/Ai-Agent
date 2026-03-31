"""
bot.py — Главный файл: Telegram-бот + агентный цикл с Claude.

Это «сердце» всего проекта. Здесь:
1. Telegram-бот принимает сообщения от пользователей
2. Агентный цикл отправляет их в Claude API
3. Claude решает какие функции вызвать
4. Бот выполняет функции и возвращает результат в Claude
5. Claude формирует финальный ответ
6. Бот отправляет ответ пользователю в Telegram

Агентный цикл — это while-цикл:
  Пока Claude хочет вызывать функции → выполняй и отправляй результат обратно.
  Когда Claude готов ответить текстом → отправь текст пользователю.
"""

import os
import atexit
import fcntl
import logging
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
import anthropic

import sheets
from config import SYSTEM_PROMPT, CLAUDE_MODEL, ALLOWED_USERS, MAX_HISTORY, MAX_TOKENS
from tools import TOOL_DEFINITIONS, execute_tool

# ============================================================
# ЗАГРУЗКА НАСТРОЕК
# ============================================================
# .env файл содержит секретные ключи. load_dotenv() читает их.
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")        # Токен Telegram-бота
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")   # API-ключ Claude
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")         # ID Google-таблицы
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")  # Путь к JSON-ключу Google

# Проверяем что все ключи на месте
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в .env файле!")
if not ANTHROPIC_API_KEY:
    raise ValueError("❌ ANTHROPIC_API_KEY не найден в .env файле!")
if not SPREADSHEET_ID:
    raise ValueError("❌ SPREADSHEET_ID не найден в .env файле!")

# ============================================================
# ИНИЦИАЛИЗАЦИЯ
# ============================================================
# Настраиваем логирование (чтобы видеть что происходит)
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Создаём клиент Claude
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# История сообщений для каждого пользователя
# Ключ — Telegram user ID, значение — список сообщений
user_histories: dict[int, list] = {}

# Защита от дублей апдейтов и от повторного /start за короткое время.
_recent_update_ids_queue: list[int] = []
_recent_update_ids_set: set[int] = set()
_max_tracked_updates = 5000
_start_cooldown_seconds = 30.0
_last_start_by_user: dict[int, float] = {}

# Держим дескриптор lock-файла открытым, чтобы lock не снимался во время работы.
_instance_lock_file = None


def _acquire_single_instance_lock() -> bool:
    """Разрешить запуск только одного процесса бота на машине."""
    global _instance_lock_file

    lock_path = Path("/tmp/ai_agent_bot.lock")
    lock_file = lock_path.open("w")

    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        _instance_lock_file = lock_file

        def _release_lock() -> None:
            try:
                if _instance_lock_file is not None:
                    fcntl.flock(_instance_lock_file.fileno(), fcntl.LOCK_UN)
                    _instance_lock_file.close()
            except Exception:
                pass

        atexit.register(_release_lock)
        return True

    except BlockingIOError:
        lock_file.close()
        return False


def _is_duplicate_update(update: Update) -> bool:
    """Вернуть True, если этот update_id уже обрабатывался в текущем процессе."""
    if update.update_id is None:
        return False

    update_id = int(update.update_id)
    if update_id in _recent_update_ids_set:
        return True

    _recent_update_ids_queue.append(update_id)
    _recent_update_ids_set.add(update_id)

    if len(_recent_update_ids_queue) > _max_tracked_updates:
        old_id = _recent_update_ids_queue.pop(0)
        _recent_update_ids_set.discard(old_id)

    return False


# ============================================================
# АГЕНТНЫЙ ЦИКЛ — САМАЯ ВАЖНАЯ ЧАСТЬ
# ============================================================

async def agent_loop(user_message: str, user_id: int) -> str:
    """
    Агентный цикл: отправляет сообщение в Claude и обрабатывает tool calls.

    Как работает:
    1. Отправляем сообщение пользователя + историю в Claude
    2. Если Claude хочет вызвать функцию (tool_use) → выполняем и отправляем результат
    3. Повторяем пока Claude не ответит текстом (stop_reason == "end_turn")
    4. Возвращаем текстовый ответ

    Максимум 10 итераций (защита от бесконечного цикла).
    """

    # Получаем или создаём историю для пользователя
    if user_id not in user_histories:
        user_histories[user_id] = []

    history = user_histories[user_id]

    # Добавляем новое сообщение пользователя
    history.append({"role": "user", "content": user_message})

    # Обрезаем историю если она слишком длинная
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
        user_histories[user_id] = history

    # Подставляем текущую дату в system prompt
    system_prompt = SYSTEM_PROMPT.format(
        current_date=datetime.now().strftime("%d.%m.%Y")
    )

    # --- АГЕНТНЫЙ ЦИКЛ ---
    max_iterations = 10  # Защита от бесконечного цикла

    for iteration in range(max_iterations):
        logger.info(f"🔄 Итерация {iteration + 1} для пользователя {user_id}")

        # Отправляем запрос в Claude API
        response = claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            tools=TOOL_DEFINITIONS,
            messages=history,
        )

        logger.info(f"   stop_reason: {response.stop_reason}")

        # ---- ВАРИАНТ 1: Claude хочет вызвать функцию ----
        if response.stop_reason == "tool_use":
            # Добавляем ответ Claude (с tool_use блоками) в историю
            history.append({"role": "assistant", "content": response.content})

            # Обрабатываем каждый tool_use блок
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info(f"   🔧 Вызов: {block.name}({block.input})")

                    # Выполняем функцию
                    result = execute_tool(block.name, block.input)
                    logger.info(f"   ✅ Результат: {result[:200]}...")

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            # Добавляем результаты в историю и продолжаем цикл
            history.append({"role": "user", "content": tool_results})
            continue  # Следующая итерация — Claude обработает результаты

        # ---- ВАРИАНТ 2: Claude готов ответить текстом ----
        elif response.stop_reason == "end_turn":
            # Собираем текстовый ответ
            assistant_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    assistant_text += block.text

            # Добавляем ответ ассистента в историю
            history.append({"role": "assistant", "content": assistant_text})

            return assistant_text

        # ---- ВАРИАНТ 3: Что-то неожиданное ----
        else:
            logger.warning(f"   ⚠️ Неожиданный stop_reason: {response.stop_reason}")
            return "Извини, произошла ошибка. Попробуй ещё раз."

    # Если вышли из цикла — слишком много итераций
    return "Извини, запрос оказался слишком сложным. Попробуй разбить его на части."


# ============================================================
# ОБРАБОТЧИКИ TELEGRAM
# ============================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовые сообщения от пользователей."""

    if _is_duplicate_update(update):
        logger.info(f"⏭️ Дубликат update_id={update.update_id} пропущен (message)")
        return

    user = update.effective_user
    user_id = user.id
    message_text = update.message.text

    # Проверяем доступ (если список ALLOWED_USERS не пустой)
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        await update.message.reply_text(
            "⛔ У вас нет доступа к этому боту. Обратитесь к администратору."
        )
        return

    logger.info(f"📩 Сообщение от {user.first_name} ({user_id}): {message_text}")

    # Показываем что бот "печатает"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        # Запускаем агентный цикл
        response_text = await agent_loop(message_text, user_id)

        # Отправляем ответ (разбиваем на части если длинный)
        # Telegram ограничивает сообщения 4096 символами
        if len(response_text) <= 4096:
            await update.message.reply_text(response_text)
        else:
            # Разбиваем на части
            for i in range(0, len(response_text), 4096):
                await update.message.reply_text(response_text[i:i + 4096])

    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)
        await update.message.reply_text(
            "😔 Произошла ошибка при обработке запроса. Попробуй ещё раз через минуту."
        )


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start — приветствие."""
    if _is_duplicate_update(update):
        logger.info(f"⏭️ Дубликат update_id={update.update_id} пропущен (/start)")
        return

    user_id = update.effective_user.id
    now = time.monotonic()
    last_start = _last_start_by_user.get(user_id, 0.0)
    if now - last_start < _start_cooldown_seconds:
        logger.info(f"⏭️ Повторный /start за {now - last_start:.2f}s пропущен для user_id={user_id}")
        return
    _last_start_by_user[user_id] = now

    await update.message.reply_text(
        "👋 Привет! Я помощник колбасного цеха.\n\n"
        "📌 Быстрые команды (без AI, моментально):\n"
        "/today — заказы на сегодня\n"
        "/purchase — что нужно закупить\n"
        "/stats — выручка за неделю\n"
        "/clear — очистить историю\n\n"
        "Или просто напиши что нужно, например:\n"
        "«Запиши 50 кг докторской для Алии на пятницу»"
    )


async def handle_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /clear — очистка истории."""
    if _is_duplicate_update(update):
        logger.info(f"⏭️ Дубликат update_id={update.update_id} пропущен (/clear)")
        return

    user_id = update.effective_user.id
    user_histories.pop(user_id, None)
    await update.message.reply_text("🧹 История очищена!")


# ============================================================
# БЫСТРЫЕ КОМАНДЫ (БЕЗ CLAUDE API — 0 ТОКЕНОВ!)
# ============================================================

async def handle_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /today — заказы на сегодня. Без Claude API."""
    if _is_duplicate_update(update):
        logger.info(f"⏭️ Дубликат update_id={update.update_id} пропущен (/today)")
        return

    try:
        data = sheets.get_today_orders()

        if data["count"] == 0:
            await update.message.reply_text("📋 Активных заказов нет.")
            return

        lines = [f"📋 *Заказы на {data['date']}:*\n"]

        for i, order in enumerate(data["orders"], 1):
            client = order.get("Клиент", "?")
            product = order.get("Продукт", "?")
            kg = order.get("Кол-во (кг)", "?")
            price = order.get("Цена (₸)", "?")
            status = order.get("Статус", "?")
            lines.append(f"{i}. {client} — {product} {kg} кг ({price} ₸) _{status}_")

        lines.append(f"\n*Итого: {data['total_kg']} кг, {data['total_price']} ₸*")

        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.error(f"❌ /today ошибка: {e}", exc_info=True)
        await update.message.reply_text("Ошибка при загрузке заказов. Проверь таблицу.")


async def handle_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /purchase — список закупок сырья. Без Claude API."""
    if _is_duplicate_update(update):
        logger.info(f"⏭️ Дубликат update_id={update.update_id} пропущен (/purchase)")
        return

    try:
        data = sheets.get_purchase_list()

        if data["orders_count"] == 0:
            await update.message.reply_text("🛒 Новых заказов нет — закупки не нужны.")
            return

        lines = [f"🛒 *Закупка сырья* ({data['orders_count']} новых заказов):\n"]

        # Продукты
        lines.append("*Производство:*")
        for product, kg in data["products"].items():
            lines.append(f"• {product} — {kg} кг")

        # Сырьё
        totals = data["totals"]
        lines.append("\n*Нужно закупить:*")
        if totals.get("beef_kg", 0) > 0:
            lines.append(f"• Говядина — {totals['beef_kg']} кг")
        if totals.get("pork_kg", 0) > 0:
            lines.append(f"• Свинина — {totals['pork_kg']} кг")
        if totals.get("fat_kg", 0) > 0:
            lines.append(f"• Шпик — {totals['fat_kg']} кг")
        if totals.get("spices_kg", 0) > 0:
            lines.append(f"• Специи — {totals['spices_kg']} кг")
        if totals.get("casing_m", 0) > 0:
            lines.append(f"• Оболочка — {totals['casing_m']} м")

        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.error(f"❌ /purchase ошибка: {e}", exc_info=True)
        await update.message.reply_text("Ошибка при расчёте закупок. Проверь таблицу.")


async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /stats — статистика за неделю. Без Claude API."""
    if _is_duplicate_update(update):
        logger.info(f"⏭️ Дубликат update_id={update.update_id} пропущен (/stats)")
        return

    try:
        data = sheets.get_weekly_stats()

        if data["total_orders"] == 0:
            await update.message.reply_text(
                f"📊 За период {data['period']} заказов не было."
            )
            return

        lines = [
            f"📊 *Статистика за {data['period']}:*\n",
            f"• Заказов: {data['total_orders']}",
            f"• Объём: {data['total_kg']} кг",
            f"• Выручка: {data['total_revenue']:,.0f} ₸",
        ]

        if data["top_products"]:
            lines.append("\n*Топ продукты:*")
            for product, kg in data["top_products"]:
                lines.append(f"• {product} — {kg} кг")

        if data["top_clients"]:
            lines.append("\n*Топ клиенты:*")
            for client, revenue in data["top_clients"]:
                lines.append(f"• {client} — {revenue:,.0f} ₸")

        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.error(f"❌ /stats ошибка: {e}", exc_info=True)
        await update.message.reply_text("Ошибка при расчёте статистики. Проверь таблицу.")


# ============================================================
# ЗАПУСК БОТА
# ============================================================

def main():
    """Запуск бота."""
    logger.info("🚀 Запуск бота колбасного цеха...")

    if not _acquire_single_instance_lock():
        logger.error("❌ Бот уже запущен. Останови старый процесс или используй restart.sh")
        return

    # Инициализируем Google Sheets
    sheets.init(CREDENTIALS_FILE, SPREADSHEET_ID)

    # Создаём Telegram-бота
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("clear", handle_clear))
    app.add_handler(CommandHandler("today", handle_today))        # 0 токенов!
    app.add_handler(CommandHandler("purchase", handle_purchase))  # 0 токенов!
    app.add_handler(CommandHandler("stats", handle_stats))        # 0 токенов!
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запускаем!
    logger.info("✅ Бот запущен и готов к работе!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()