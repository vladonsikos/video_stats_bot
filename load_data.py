import asyncio
import json
import os
from datetime import datetime
from db import init_db, get_db_connection

JSON_FILE = "videos.json"
BATCH_SIZE = 100

def parse_datetime(dt_str):
    """Преобразует строку с датой в объект datetime (aware)"""
    # Пример: '2025-08-19T08:54:35+00:00'
    return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))

async def load_data():
    print("Инициализация таблиц...")
    await init_db()

    print(f"Загрузка данных из {JSON_FILE}...")
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        videos = data.get('videos', [])

    conn = await get_db_connection()
    try:
        await conn.execute("TRUNCATE video_snapshots, videos RESTART IDENTITY CASCADE")

        video_records = []
        for v in videos:
            video_records.append((
                v['id'],
                v['creator_id'],
                parse_datetime(v['video_created_at']),
                v['views_count'],
                v['likes_count'],
                v['comments_count'],
                v['reports_count'],
                parse_datetime(v['created_at']),
                parse_datetime(v['updated_at'])
            ))
            if len(video_records) >= BATCH_SIZE:
                await conn.executemany('''
                    INSERT INTO videos (id, creator_id, video_created_at, views_count, likes_count, comments_count, reports_count, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ''', video_records)
                video_records.clear()
        if video_records:
            await conn.executemany('''
                INSERT INTO videos (id, creator_id, video_created_at, views_count, likes_count, comments_count, reports_count, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ''', video_records)

        snapshot_records = []
        for v in videos:
            for s in v.get('snapshots', []):
                snapshot_records.append((
                    s['id'],
                    s['video_id'],
                    s['views_count'],
                    s['likes_count'],
                    s['comments_count'],
                    s['reports_count'],
                    s['delta_views_count'],
                    s['delta_likes_count'],
                    s['delta_comments_count'],
                    s['delta_reports_count'],
                    parse_datetime(s['created_at']),
                    parse_datetime(s['updated_at'])
                ))
                if len(snapshot_records) >= BATCH_SIZE:
                    await conn.executemany('''
                        INSERT INTO video_snapshots
                        (id, video_id, views_count, likes_count, comments_count, reports_count,
                         delta_views_count, delta_likes_count, delta_comments_count, delta_reports_count,
                         created_at, updated_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    ''', snapshot_records)
                    snapshot_records.clear()
        if snapshot_records:
            await conn.executemany('''
                INSERT INTO video_snapshots
                (id, video_id, views_count, likes_count, comments_count, reports_count,
                 delta_views_count, delta_likes_count, delta_comments_count, delta_reports_count,
                 created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ''', snapshot_records)

        print("Данные успешно загружены.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(load_data())
