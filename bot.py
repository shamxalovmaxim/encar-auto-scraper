"""
Главный модуль Telegram-бота управления парсером Encar.
Включает управление, статус, дампы, экспорт в Excel и CSV, фоновый планировщик.
"""

import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    FSInputFile,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN, ADMIN_ID, SCHEDULE_INTERVAL_MINUTES
from database import init_db, get_total_cars_count
from parser import EncarParser, state as parser_state
from exporter import export_cars_to_file, get_database_dump_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()
parser_instance = EncarParser(concurrency_limit=5, page_size=20)
active_task: asyncio.Task | None = None


def get_admin_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="▶️ Запустить парсер"), KeyboardButton(text="⏹ Остановить")],
        [KeyboardButton(text="📊 Статус системы"), KeyboardButton(text="💾 Скачать дамп БД")],
        [KeyboardButton(text="📁 Экспорт в Excel"), KeyboardButton(text="📄 Экспорт в CSV")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


@dp.message(CommandStart())
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Доступ ограничен. Этот бот предназначен только для администратора.")
        return

    text = (
        "🤖 **Панель управления парсером Encar.com**\n\n"
        "Выберите действие на клавиатуре ниже:\n"
        "• **Запустить** — начать сбор актуальных объявлений\n"
        "• **Остановить** — корректно прервать процесс\n"
        "• **Статус** — текущее состояние и количество авто в базе\n"
        "• **Экспорт в Excel / CSV** — получить выгрузку в нужном формате\n"
        "• **Скачать дамп** — получить сырой файл базы данных SQLite"
    )
    await message.answer(text, reply_markup=get_admin_keyboard(), parse_mode="Markdown")


async def run_parser_job():
    if parser_state.is_running:
        logger.warning("Попытка запуска: парсер уже работает.")
        return
    await parser_instance.run(max_pages=10)


@dp.message(F.text == "▶️ Запустить парсер")
async def btn_start_parser(message: Message):
    global active_task
    if not is_admin(message.from_user.id):
        return

    if parser_state.is_running:
        await message.answer("⚠️ Парсер уже запущен и собирает данные.")
        return

    active_task = asyncio.create_task(run_parser_job())
    await message.answer("🚀 Парсер успешно запущен в фоновом режиме. Вы можете продолжать пользоваться ботом.")


@dp.message(F.text == "⏹ Остановить")
async def btn_stop_parser(message: Message):
    if not is_admin(message.from_user.id):
        return

    if not parser_state.is_running:
        await message.answer("ℹ️ Парсер сейчас не активен.")
        return

    parser_state.stop_requested = True
    await message.answer("⏳ Сигнал остановки отправлен. Процесс завершится после обработки текущего запроса.")


@dp.message(F.text == "📊 Статус системы")
async def btn_status(message: Message):
    if not is_admin(message.from_user.id):
        return

    total_cars = await get_total_cars_count()
    status_str = "🟢 Работает" if parser_state.is_running else "⚪️ Простаивает"

    text = (
        f"📊 **Текущее состояние системы**\n\n"
        f"• Статус парсера: {status_str}\n"
        f"• Обработано в текущей сессии: `{parser_state.total_parsed}` авто\n"
        f"• Текущая страница: `{parser_state.current_page}`\n"
        f"• Всего авто в базе данных: `{total_cars}` шт.\n"
        f"• Автоматический сбор: каждые {SCHEDULE_INTERVAL_MINUTES} мин."
    )
    if parser_state.last_error:
        text += f"\n\n⚠️ Последняя ошибка: `{parser_state.last_error}`"

    await message.answer(text, parse_mode="Markdown")


@dp.message(F.text == "📁 Экспорт в Excel")
async def btn_export_excel(message: Message):
    if not is_admin(message.from_user.id):
        return

    msg = await message.answer("⏳ Формирование Excel-файла, пожалуйста, подождите...")
    try:
        file_path = await export_cars_to_file(format_type="excel")
        document = FSInputFile(file_path)
        await message.answer_document(document, caption="📊 Актуальная выгрузка автомобилей Encar (Excel).")
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка экспорта: {e}")


@dp.message(F.text == "📄 Экспорт в CSV")
async def btn_export_csv(message: Message):
    if not is_admin(message.from_user.id):
        return

    msg = await message.answer("⏳ Формирование CSV-файла, пожалуйста, подождите...")
    try:
        file_path = await export_cars_to_file(format_type="csv")
        document = FSInputFile(file_path)
        await message.answer_document(document, caption="📄 Актуальная выгрузка автомобилей Encar (CSV с UTF-8 BOM).")
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка экспорта CSV: {e}")


@dp.message(F.text == "💾 Скачать дамп БД")
async def btn_dump_db(message: Message):
    if not is_admin(message.from_user.id):
        return

    try:
        db_file = get_database_dump_file()
        document = FSInputFile(db_file)
        await message.answer_document(document, caption="💾 Полный дамп базы данных SQLite (encar_cars.db).")
    except Exception as e:
        await message.answer(f"❌ Не удалось получить файл базы данных: {e}")


async def main():
    print(">>> Инициализация базы данных...")
    await init_db()
    print(">>> База данных готова.")

    if SCHEDULE_INTERVAL_MINUTES > 0:
        scheduler.add_job(run_parser_job, "interval", minutes=SCHEDULE_INTERVAL_MINUTES)
        scheduler.start()
        print(f">>> Планировщик активен: интервал {SCHEDULE_INTERVAL_MINUTES} мин.")

    print(">>> Запуск Telegram-бота (polling)...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    print(">>> Точка входа bot.py запущена")
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print(">>> Бот остановлен.")