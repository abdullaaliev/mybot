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
    raise ValueError("API_TOKEN не найден")

# --- Google Sheets ---
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

creds_raw = os.getenv("GOOGLE_CREDS")

if creds_raw is None:
    raise ValueError("GOOGLE_CREDS не найден")

creds_dict = json.loads(creds_raw)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)

client = gspread.authorize(creds)

# --- ОСНОВНАЯ ТАБЛИЦА ---
sheet = client.open("Отчет").sheet1

# --- ЛИСТ ПОЛЬЗОВАТЕЛЕЙ ---
try:
    users_sheet = client.open("Отчет").worksheet("Users")
except:
    users_sheet = client.open("Отчет").add_worksheet(title="Users", rows=1000, cols=2)
    users_sheet.append_row(["UserID"])

# --- Bot ---
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Constants
PRICE = 80
ADMIN_ID = 8482392419
REMINDER_TIME = time(18, 0)
ACCESS_CODE = "2818"

# State
user_daily_log: Dict[int, Dict] = {}
users: Set[int] = set()


# --- ПРОВЕРКА ВЕРИФИКАЦИИ ---
def is_verified(user_id: int) -> bool:
    try:
        data = users_sheet.get_all_values()
        return str(user_id) in [row[0] for row in data]
    except:
        return False


# --- ДОБАВИТЬ ПОЛЬЗОВАТЕЛЯ ---
def add_verified(user_id: int):
    users_sheet.append_row([str(user_id)])


# --- СТАРТ ---
@dp.message(F.text == "/start")
async def start(message: Message):
    if is_verified(message.from_user.id):
        await message.answer("👋 Привет! Введи количество изделий")
    else:
        await message.answer("🔐 Введи код доступа")


# --- ОБРАБОТКА КОДА ---
@dp.message(F.text)
async def verify_or_data(message: Message):
    user_id = message.from_user.id

    # если не верифицирован
    if not is_verified(user_id):
        if message.text == ACCESS_CODE:
            add_verified(user_id)
            users.add(user_id)

            await message.answer(
                "✅ Доступ открыт!\n\nТеперь отправь количество изделий"
            )
        else:
            await message.answer("❌ Неверный код")
        return

    # дальше обычная логика
    if message.text.startswith("/"):
        return

    if not message.text.isdigit():
        await message.answer("❌ Пиши только число")
        return

    users.add(user_id)

    count = int(message.text)
    today = datetime.now().strftime("%d.%m.%Y")

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

    await message.answer(f"✅ Принято: {count}\n💰 ЗП: {salary} ₽")

    asyncio.create_task(
        write_to_sheet(today, name, username, user_id, count, salary)
    )


async def write_to_sheet(date, name, username, user_id, count, salary):
    await asyncio.to_thread(
        sheet.append_row,
        [date, name, username, user_id, count, salary]
    )


# --- TOTAL (ТОЛЬКО ДЛЯ ТЕБЯ) ---
@dp.message(F.text == "/total")
async def total_month(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет доступа")
        return

    now = datetime.now()
    data = await asyncio.to_thread(sheet.get_all_records)

    total_sum = 0

    for row in data:
        try:
            row_date = datetime.strptime(row["Дата"], "%d.%m.%Y")

            if row_date.month == now.month and row_date.year == now.year:
                total_sum += int(row["ЗП"])

        except:
            continue

    await message.answer(f"💰 Общая ЗП за месяц: {total_sum} ₽")


# --- МЕСЯЦ ---
@dp.message(F.text == "/month")
async def my_month(message: Message):
    user_id = str(message.from_user.id)
    now = datetime.now()

    data = await asyncio.to_thread(sheet.get_all_records)

    total_salary = 0

    for row in data:
        try:
            row_date = datetime.strptime(row["Дата"], "%d.%m.%Y")

            if (
                str(row["UserID"]) == user_id and
                row_date.month == now.month and
                row_date.year == now.year
            ):
                total_salary += int(row["ЗП"])

        except:
            continue

    await message.answer(f"💰 Твоя ЗП за месяц: {total_salary} ₽")


# --- НАПОМИНАНИЕ ---
async def wait_until(target_time: time):
    while True:
        now = datetime.now()
        target = datetime.combine(now.date(), target_time)

        if now >= target:
            target = target.replace(day=now.day + 1)

        await asyncio.sleep((target - now).total_seconds())
        return


async def reminder_loop():
    while True:
        await wait_until(REMINDER_TIME)

        for user_id in users:
            try:
                await bot.send_message(user_id, "⏰ Сдайте отчёт за сегодня")
            except:
                pass


# --- ЗАПУСК ---
async def main():
    print("Бот запущен 🚀")
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
