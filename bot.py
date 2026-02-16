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

# Промпт с подробными правилами и примерами
SYSTEM_PROMPT = """
Ты — AI, который переводит вопросы на русском языке в SQL-запросы для PostgreSQL.

Таблицы:
- videos (id, creator_id, video_created_at, views_count, likes_count, comments_count, reports_count, created_at, updated_at)
- video_snapshots (id, video_id, views_count, likes_count, comments_count, reports_count, delta_views_count, delta_likes_count, delta_comments_count, delta_reports_count, created_at, updated_at)

Правила:
1. Всегда используй точные имена полей из таблиц: например, "views_count", а не "views".
2. Если вопрос про итоговую статистику — используй таблицу videos. Если про почасовые изменения — video_snapshots.
3. Строковые значения (например, id креатора) всегда заключай в одинарные кавычки: 'aca1061a9d324ecf8c3fa2bb32d7be63'.
4. Даты на русском (например, "28 ноября 2025") преобразуй в формат '2025-11-28' для SQL. Если указано время, добавляй его: '2025-11-28 10:00:00'.
5. Временные интервалы: "с 10:00 до 15:00" означает created_at >= '2025-11-28 10:00:00' AND created_at < '2025-11-28 15:00:00'.
6. Числа могут содержать пробелы (например, "10 000") — удали пробелы и используй число 10000.
7. Отвечай только SQL-запросом, без пояснений и дополнительного текста. Не используй markdown, не обрамляй код в ```sql.
8. Результат запроса должен быть одним числом (используй COUNT, SUM и т.д.).
9. В таблице video_snapshots нет поля creator_id. Чтобы получить снапшоты для конкретного креатора, нужно сначала выбрать id видео из таблицы videos, а затем использовать их в условии для video_snapshots. Всегда используй подзапрос: video_id IN (SELECT id FROM videos WHERE creator_id = '...'). Никогда не используй JOIN для связи по creator_id.

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

Вопрос: "Сколько видео у креатора с id aca1061a9d324ecf8c3fa2bb32d7be63 набрали больше 10 000 просмотров по итоговой статистике?"
Ответ: SELECT COUNT(*) FROM videos WHERE creator_id = 'aca1061a9d324ecf8c3fa2bb32d7be63' AND views_count > 10000;

Вопрос: "Какое общее количество просмотров у всех видео?"
Ответ: SELECT SUM(views_count) FROM videos;

Вопрос: "Сколько снапшотов было 27 ноября 2025?"
Ответ: SELECT COUNT(*) FROM video_snapshots WHERE created_at::date = '2025-11-27';

Вопрос: "На сколько просмотров суммарно выросли все видео креатора с id cd87be38b50b4fdd8342bb3c383f3c7d в промежутке с 10:00 до 15:00 28 ноября 2025 года?"
Ответ: SELECT SUM(delta_views_count) FROM video_snapshots WHERE video_id IN (SELECT id FROM videos WHERE creator_id = 'cd87be38b50b4fdd8342bb3c383f3c7d') AND created_at >= '2025-11-28 10:00:00' AND created_at < '2025-11-28 15:00:00';

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
        lines = sql.split('\n')
        clean_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('```') or stripped == '':
                continue
            clean_lines.append(line.rstrip())
        sql = '\n'.join(clean_lines).strip()
        if not sql.lower().startswith('select'):
            for i, line in enumerate(clean_lines):
                if line.strip().lower().startswith('select'):
                    sql = '\n'.join(clean_lines[i:])
                    break
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
    except asyncpg.PostgresError as e:
        logging.error(f"PostgreSQL error: {e}\nSQL: {sql}")
        return "0"
    except Exception as e:
        logging.error(f"Unexpected error: {e}\nSQL: {sql}")
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
