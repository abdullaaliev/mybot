import asyncio
import os
import json
from datetime import datetime, time, timedelta
from typing import Dict, Set

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message

import gspread
from oauth2client.service_account import ServiceAccountCredentials

API_TOKEN = os.getenv("API_TOKEN")

if not API_TOKEN:
    raise ValueError("API_TOKEN не найден в переменных окружения")

# --- Google Sheets ---
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

creds_raw = os.getenv("GOOGLE_CREDS")

if creds_raw is None:
    raise ValueError("GOOGLE_CREDS не найден в переменных окружения")

creds_dict = json.loads(creds_raw)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)

client = gspread.authorize(creds)
sheet = client.open("Отчет").sheet1

# --- Bot ---
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Constants
PRICE = 80  # стартовая цена
ADMIN_ID = 8482392419
REMINDER_TIME = time(18, 0)

# State management
user_daily_log: Dict[int, Dict] = {}
users: Set[int] = set()


# --- СТАРТ ---
@dp.message(F.text == "/start")
async def start(message: Message):
    users.add(message.from_user.id)
    await message.answer(
        "👋 Привет!\n\n"
        "✂️ Напиши, сколько изделий ты изготовила сегодня.\n"
        "Пример: 25"
    )


# --- ID ---
@dp.message(F.text == "/id")
async def get_id(message: Message):
    await message.answer(f"Твой ID: {message.from_user.id}")


# --- ЗАПИСЬ ---
@dp.message(F.text & ~F.text.startswith("/"))
async def save_data(message: Message):
    if not message.text.isdigit():
        await message.answer("❌ Пиши только число")
        return

    user_id = message.from_user.id
    users.add(user_id)

    count = int(message.text)
    today = datetime.now().strftime("%d.%m.%Y")

    # Проверка на дублирование
    if user_id in user_daily_log and user_daily_log[user_id]["date"] == today:
        await message.answer("⚠️ Уже отправляла сегодня")
        return

    name = message.from_user.full_name or "Unknown"
    username = message.from_user.username or ""

    user_daily_log[user_id] = {
        "date": today,
        "count": count
    }

    salary = count * PRICE

    await message.answer(
        f"✅ Принято: {count}\n���� ЗП: {salary} ₽"
    )

    asyncio.create_task(
        write_to_sheet(today, name, username, user_id, count, salary)
    )


async def write_to_sheet(date: str, name: str, username: str, user_id: int, count: int, salary: int):
    """Асинхронно записывает данные в Google Sheets"""
    try:
        await asyncio.to_thread(
            sheet.append_row,
            [date, name, username, user_id, count, salary]
        )
    except Exception as e:
        print(f"Ошибка при записи в Google Sheets: {e}")


# --- СМЕНА ЦЕНЫ ---
@dp.message(F.text.startswith("/setprice"))
async def set_price(message: Message):
    global PRICE

    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет доступа")
        return

    parts = message.text.split()

    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("❌ Используй: /setprice 80")
        return

    new_price = int(parts[1])
    if new_price <= 0:
        await message.answer("❌ Цена должна быть больше 0")
        return

    PRICE = new_price
    await message.answer(f"✅ Новая цена: {PRICE} ₽")


# --- МОЙ МЕСЯЦ ---
@dp.message(F.text == "/month")
async def my_month(message: Message):
    user_id = str(message.from_user.id)
    now = datetime.now()

    try:
        data = await asyncio.to_thread(sheet.get_all_records)
    except Exception as e:
        await message.answer(f"❌ Ошибка при чтении данных: {e}")
        return

    total_count = 0
    total_salary = 0

    for row in data:
        try:
            row_date = datetime.strptime(row["Дата"], "%d.%m.%Y")

            if (
                str(row["UserID"]) == user_id and
                row_date.month == now.month and
                row_date.year == now.year
            ):
                count = int(row["Кол-во"])
                total_count += count
                total_salary += count * PRICE

        except (ValueError, KeyError):
            continue

    await message.answer(
        f"💰 За месяц:\n\n"
        f"Изделий: {total_count}\n"
        f"ЗП: {total_salary} ₽"
    )


# --- ОБЩИЙ ОТЧЁТ ---
@dp.message(F.text == "/total")
async def total_month(message: Message):
    now = datetime.now()

    try:
        data = await asyncio.to_thread(sheet.get_all_records)
    except Exception as e:
        await message.answer(f"❌ Ошибка при чтении данных: {e}")
        return

    stats: Dict[str, int] = {}
    total_sum = 0

    for row in data:
        try:
            row_date = datetime.strptime(row["Дата"], "%d.%m.%Y")

            if row_date.month == now.month and row_date.year == now.year:
                name = row["Имя"]
                count = int(row["Кол-во"])
                salary = count * PRICE

                stats[name] = stats.get(name, 0) + salary
                total_sum += salary

        except (ValueError, KeyError):
            continue

    if not stats:
        await message.answer("📊 Нет данн��х за текущий месяц")
        return

    text = "📊 Выплаты за месяц:\n\n"
    for name, money in sorted(stats.items()):
        text += f"{name} — {money} ₽\n"

    text += f"\nИТОГО: {total_sum} ₽"
    await message.answer(text)


# --- ТАБЛИЦА ЛИДЕРОВ ЗА НЕДЕЛЮ ---
@dp.message(F.text == "/top")
async def top_week(message: Message):
    now = datetime.now()
    week_ago = now - timedelta(days=7)

    try:
        data = await asyncio.to_thread(sheet.get_all_records)
    except Exception as e:
        await message.answer(f"❌ Ошибка при чтении данных: {e}")
        return

    stats: Dict[str, int] = {}

    for row in data:
        try:
            row_date = datetime.strptime(row["Дата"], "%d.%m.%Y")

            if week_ago <= row_date <= now:
                name = row["Имя"]
                count = int(row["Кол-во"])
                stats[name] = stats.get(name, 0) + count

        except (ValueError, KeyError):
            continue

    if not stats:
        await message.answer("📊 Нет данных за последнюю неделю")
        return

    sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
    top_10 = sorted_stats[:10]

    text = "🏆 ТОП за неделю:\n\n"
    medals = ["🥇", "🥈", "🥉"]

    for idx, (name, count) in enumerate(top_10, 1):
        medal = medals[idx - 1] if idx <= 3 else f"{idx}."
        text += f"{medal} {name} — {count} шт.\n"

    await message.answer(text)


# --- НАПОМИНАНИЕ ---
async def wait_until(target_time: time) -> None:
    """Ожидает наступления определённого времени суток"""
    while True:
        now = datetime.now()
        target = datetime.combine(now.date(), target_time)

        if now >= target:
            target = target.replace(day=now.day + 1)

        delay = (target - now).total_seconds()
        await asyncio.sleep(delay)
        return


async def reminder_loop():
    """Отправляет напоминания пользователям"""
    while True:
        await wait_until(REMINDER_TIME)

        for user_id in users:
            try:
                await bot.send_message(user_id, "⏰ Сдайте отчёт за сегодня")
            except Exception as e:
                print(f"Ошибка при отправке напоминания пользователю {user_id}: {e}")


# --- ЗАПУСК ---
async def main():
    print("Бот запущен 🚀")
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
