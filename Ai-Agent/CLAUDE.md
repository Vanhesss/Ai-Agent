# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Sausage Factory Bot** — a Telegram AI agent for a sausage manufacturing plant in Kazakhstan. Uses Claude API (tool_use / function calling) for natural language understanding, order management, raw material calculation. Data lives in Google Sheets.

## Architecture

```
User (Telegram) → Python Bot (VPS) → Claude API (tool_use agent loop)
                                   ↕
                              Google Sheets
                         (Заказы / Рецептуры / Клиенты)
```

**Agent loop** (bot.py): User message → Claude API with tools → if `stop_reason == "tool_use"` execute tool & send result back → repeat up to 10 iterations → if `stop_reason == "end_turn"` return text to Telegram.

## Tech Stack

- Python 3.11+, async
- `python-telegram-bot` 21.6 (run_polling)
- `anthropic` SDK (Messages API with tool_use)
- `gspread` + `google-auth` (Google Sheets)
- `python-dotenv`
- Claude model: `claude-haiku-4-5-20251001`

## Key Files

| File | Purpose |
|------|---------|
| `config.py` | System prompt (with `{current_date}`), model selection, sheet names, `ALLOWED_USERS`, `MAX_HISTORY=20` |
| `sheets.py` | Google Sheets CRUD via gspread: orders, recipes, clients |
| `tools.py` | 8 tool definitions (JSON Schema) + `execute_tool()` dispatcher |
| `bot.py` | Telegram handlers + `agent_loop()` + Claude API calls, per-user history |
| `skills/base_skill.py` | ABC for pluggable skill modules (get_tool_definitions, execute_tool) |
| `agents/base_agent.py` | ABC with shared agent loop logic for specialized agents |

## Commands

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill TELEGRAM_TOKEN, ANTHROPIC_API_KEY, SPREADSHEET_ID

# Run
python bot.py

# Tests
pytest tests/

# Deploy (systemd on Ubuntu VPS)
sudo systemctl start sausage-bot
sudo journalctl -u sausage-bot -f
```

## Google Sheets Structure

- **Заказы**: ID | Дата | Клиент | Продукт | Кол-во (кг) | Цена (₸) | Статус | Дата отгрузки
- **Рецептуры**: Продукт | Говядина (кг) | Свинина (кг) | Шпик (кг) | Специи (кг) | Оболочка (м) | Цена за кг (₸)
- **Клиенты**: Название | Контакт | Телефон | Адрес | Скидка %

Recipes are per 100 kg of finished product. Currency: Kazakh tenge (₸).

## Coding Conventions

- Type hints on all function signatures
- Docstrings and comments in **Russian**
- Bot responds in **Russian**
- `logging` module (not print)
- f-strings for formatting
- All tool results: `json.dumps(result, ensure_ascii=False)`
- Telegram messages ≤ 4096 chars — split if longer
- Use `send_chat_action("typing")` for UX

## Claude API Pattern

```python
response = claude.messages.create(
    model=CLAUDE_MODEL, max_tokens=4096,
    system=SYSTEM_PROMPT, tools=TOOL_DEFINITIONS, messages=messages
)
# stop_reason == "tool_use" → execute tools → send tool_result back
# stop_reason == "end_turn" → return text to user
```

## Extension Points

**Skills** (`skills/`): Pluggable modules that provide additional tool definitions + handlers. Registered in bot.py by extending `ALL_TOOLS`. The bot must work without any skills loaded.

**Agents** (`agents/`): Specialized AI personalities with own system prompts and tool sets. The main bot.py agent handles everything by default; agents are optional.

## Critical Rules

1. Never break the 4 core files (config, sheets, tools, bot) — preserve their public APIs
2. The agent loop pattern is the heart of the system — preserve it
3. Google Sheets is the single source of truth — no local DB
4. New tools must follow the same JSON Schema format and return JSON strings
5. Budget-conscious: prefer Haiku model, minimize API calls
