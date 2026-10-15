"""
Модуль асинхронной работы с базой данных SQLite.
Реализует инициализацию таблиц, подсчет записей и механизм Smart Upsert:
новые авто добавляются, а у существующих обновляются цены, пробег и дата.
"""

from datetime import datetime
import json
from typing import Any
import aiosqlite

from config import DB_PATH


async def init_db():
    """Создает таблицу cars и необходимые индексы при первом запуске."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cars (
                id TEXT PRIMARY KEY,
                manufacturer TEXT,
                model TEXT,
                badge TEXT,
                badge_detail TEXT,
                year INTEGER,
                form_year INTEGER,
                mileage INTEGER,
                price INTEGER,
                fuel_type TEXT,
                transmission TEXT,
                photos_json TEXT,
                created_at TEXT,
                updated_at TEXT
            );
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_cars_created_at ON cars(created_at);")
        await db.commit()


async def get_total_cars_count() -> int:
    """Возвращает общее количество уникальных автомобилей в базе."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM cars") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def upsert_cars_batch(cars: list[dict[str, Any]]):
    """
    Пакетная вставка списка автомобилей с разрешением конфликтов по ID.
    Если запись уже есть — обновляются пробег, цена, ссылки и updated_at.
    """
    if not cars:
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    query = """
    INSERT INTO cars (
        id, manufacturer, model, badge, badge_detail,
        year, form_year, mileage, price, fuel_type,
        transmission, photos_json, created_at, updated_at
    ) VALUES (
        ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?,
        ?, ?, ?, ?
    )
    ON CONFLICT(id) DO UPDATE SET
        manufacturer = excluded.manufacturer,
        model = excluded.model,
        badge = excluded.badge,
        badge_detail = excluded.badge_detail,
        year = excluded.year,
        form_year = excluded.form_year,
        mileage = excluded.mileage,
        price = excluded.price,
        fuel_type = excluded.fuel_type,
        transmission = excluded.transmission,
        photos_json = excluded.photos_json,
        updated_at = excluded.updated_at
    """

    records = []
    for c in cars:
        photos = c.get("photos", [])
        photos_str = json.dumps(photos, ensure_ascii=False) if isinstance(photos, list) else str(photos)
        
        records.append((
            str(c.get("id")),
            c.get("manufacturer", ""),
            c.get("model", ""),
            c.get("badge", ""),
            c.get("badge_detail", ""),
            c.get("year"),
            c.get("form_year"),
            c.get("mileage"),
            c.get("price"),
            c.get("fuel_type", ""),
            c.get("transmission", ""),
            photos_str,
            now,
            now,
        ))

    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(query, records)
        await db.commit()


async def upsert_car(car: dict[str, Any]):
    """Одиночная вставка или обновление одного автомобиля."""
    await upsert_cars_batch([car])