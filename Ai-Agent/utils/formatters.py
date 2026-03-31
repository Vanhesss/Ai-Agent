"""
formatters.py — Хелперы для форматирования сообщений Telegram.
"""


def split_message(text: str, max_length: int = 4096) -> list[str]:
    """Разбить длинное сообщение на части для Telegram."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break

        # Попробовать разбить по переносу строки
        split_pos = text.rfind("\n", 0, max_length)
        if split_pos == -1:
            split_pos = max_length

        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip("\n")

    return chunks


def format_order(order: dict) -> str:
    """Форматировать заказ для отображения в Telegram."""
    return (
        f"📦 *Заказ #{order.get('ID', '?')}*\n"
        f"• Клиент: {order.get('Клиент', '—')}\n"
        f"• Продукт: {order.get('Продукт', '—')}\n"
        f"• Кол-во: {order.get('Кол-во (кг)', '—')} кг\n"
        f"• Цена: {order.get('Цена (₸)', '—')} ₸\n"
        f"• Статус: {order.get('Статус', '—')}\n"
        f"• Отгрузка: {order.get('Дата отгрузки', '—')}"
    )
