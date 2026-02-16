import asyncio
import logging
import os
import httpx
import asyncpg
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv
from db import get_db_connection

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "mistralai/mistral-7b-instruct"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

SYSTEM_PROMPT = """
Ты — AI, который переводит вопросы на русском языке в SQL-запросы для PostgreSQL.

Таблицы:
- videos (id, creator_id, video_created_at, views_count, likes_count, comments_count, reports_count, created_at, updated_at)
- video_snapshots (id, video_id, views_count, likes_count, comments_count, reports_count, delta_views_count, delta_likes_count, delta_comments_count, delta_reports_count, created_at, updated_at)

Правила:
- Вопросы могут содержать даты на русском (например, "28 ноября 2025"). Преобразуй в формат '2025-11-28' для SQL.
- Всегда используй агрегатные функции (COUNT, SUM и т.д.), чтобы результат был одним числом.
- Отвечай только SQL-запросом, без пояснений.

Примеры:
Вопрос: "Сколько всего видео есть в системе?"
Ответ: SELECT COUNT(*) FROM videos;

Вопрос: "Сколько видео у креатора с id aca1061a9d324ecf8c3fa2bb32d7be63 вышло с 1 ноября 2025 по 5 ноября 2025 включительно?"
Ответ: SELECT COUNT(*) FROM videos WHERE creator_id = 'aca1061a9d324ecf8c3fa2bb32d7be63' AND video_created_at::date BETWEEN '2025-11-01' AND '2025-11-05';

Вопрос: "На сколько просмотров в сумме выросли все видео 28 ноября 2025?"
Ответ: SELECT SUM(delta_views_count) FROM video_snapshots WHERE created_at::date = '2025-11-28';

Вопрос: "Сколько разных видео получали новые просмотры 27 ноября 2025?"
Ответ: SELECT COUNT(DISTINCT video_id) FROM video_snapshots WHERE created_at::date = '2025-11-27' AND delta_views_count > 0;

Вопрос: "Сколько видео набрало больше 100 000 просмотров за всё время?"
Ответ: SELECT COUNT(*) FROM videos WHERE views_count > 100000;

Теперь вопрос пользователя: {user_question}
"""

async def ask_llm(question: str) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "Ты переводишь вопросы в SQL. Отвечай только SQL запросом."},
            {"role": "user", "content": SYSTEM_PROMPT.format(user_question=question)}
        ],
        "temperature": 0.0,
        "max_tokens": 200
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        sql = data["choices"][0]["message"]["content"].strip()
        if sql.lower().startswith("select"):
            lines = sql.split('\n')
            for line in lines:
                if line.strip().lower().startswith("select"):
                    return line.strip()
        return sql

async def execute_sql(sql: str) -> str:
    conn = await get_db_connection()
    try:
        sql_lower = sql.lower()
        if "delete" in sql_lower or "drop" in sql_lower or "insert" in sql_lower or "update" in sql_lower:
            return "0"
        row = await conn.fetchrow(sql)
        if row and row[0] is not None:
            return str(row[0])
        else:
            return "0"
    except Exception as e:
        logging.error(f"SQL execution error: {e}\nSQL: {sql}")
        return "0"
    finally:
        await conn.close()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Привет! Я бот для аналитики видео. Задай вопрос на русском языке, и я отвечу числом.")

@dp.message()
async def handle_question(message: types.Message):
    question = message.text.strip()
    if not question:
        return

    await bot.send_chat_action(message.chat.id, action="typing")

    try:
        sql = await ask_llm(question)
        logging.info(f"SQL: {sql}")
        answer = await execute_sql(sql)
        await message.answer(answer)
    except Exception as e:
        logging.error(f"Error: {e}")
        await message.answer("Извините, произошла ошибка. Попробуйте переформулировать вопрос.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
