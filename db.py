import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS videos (
                id UUID PRIMARY KEY,
                creator_id TEXT NOT NULL,
                video_created_at TIMESTAMPTZ NOT NULL,
                views_count INT NOT NULL,
                likes_count INT NOT NULL,
                comments_count INT NOT NULL,
                reports_count INT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS video_snapshots (
                id UUID PRIMARY KEY,
                video_id UUID REFERENCES videos(id) ON DELETE CASCADE,
                views_count INT NOT NULL,
                likes_count INT NOT NULL,
                comments_count INT NOT NULL,
                reports_count INT NOT NULL,
                delta_views_count INT NOT NULL,
                delta_likes_count INT NOT NULL,
                delta_comments_count INT NOT NULL,
                delta_reports_count INT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
        ''')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_snapshots_video_id ON video_snapshots(video_id)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_snapshots_created_at ON video_snapshots(created_at)')
    finally:
        await conn.close()

async def get_db_connection():
    return await asyncpg.connect(DATABASE_URL)
