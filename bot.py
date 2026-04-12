import asyncio
import os
import json
from datetime import datetime, time

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message

import gspread
from oauth2client.service_account import ServiceAccountCredentials

API_TOKEN = os.getenv("API_TOKEN")

# --- Google Sheets ---
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

creds_raw = os.getenv("GOOGLE_CREDS")

if creds_raw is None:
    raise ValueError("GOOGLE_CREDS не найден")

creds_dict = json.loads(creds_raw)

creds = ServiceAccountCredentials.from_json_keyfile_dict(
    creds_dict, scope
)

client = gspread.authorize(creds)
sheet = client.open("Отчет").sheet1

# --- Bot ---
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

user_daily_log = {}
users = set()

PRICE = 80  # начальная цена
ADMIN_ID = 8482392419


# --- Старт ---
@dp.message(F.text == "/start")
async def start(message: Message):
    users.add(message.from_user.id)

    await message.answer(
        "👋 Привет!\n\n"
        "✂️ Напиши, сколько изделий ты изготовила сегодня.\n\n"
        "Пример: 25"
    )


# --- Узнать свой ID ---
@dp.message(F.text == "/id")
async def get_id(message: Message):
    await message.answer(f"Твой ID: {message.from_user.id}")


# --- Запись ---
@dp.message(F.text & ~F.text.startswith("/"))
async def save_data(message: Message):
    if not message.text.isdigit():
        await message.answer("❌ Пиши только число")
        return

    user_id = message.from_user.id
    users.add(user_id)

    count = int(message.text)
    today = datetime.now().strftime("%d.%m.%Y")

    if user_id in user_daily_log and user_daily_log[user_id]["date"] == today:
        await message.answer("⚠️ Уже отправляла сегодня")
        return

    name = message.from_user.full_name
    username = message.from_user.username or ""

    user_daily_log[user_id] = {
        "date": today,
        "count": count
    }

    salary = count * PRICE

    await message.answer(
        f"✅ Принято: {count}\n💰 ЗП: {salary} ₽"
    )

    asyncio.create_task(write_to_sheet(today, name, username, user_id, count, salary))


async def write_to_sheet(date, name, username, user_id, count, salary):
    await asyncio.to_thread(
        sheet.append_row,
        [date, name, username, user_id, count, salary]
    )


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

    PRICE = int(parts[1])

    await message.answer(f"✅ Новая цена: {PRICE} ₽")


# --- МЕСЯЦ ---
@dp.message(F.text == "/total")
async def total_month(message: Message):
    now = datetime.now()
    data = sheet.get_all_records()

    stats = {}
    total_sum = 0

    for row in data:
        try:
            row_date = datetime.strptime(row["Дата"], "%d.%m.%Y")

            if row_date.month == now.month and row_date.year == now.year:
                name = row["Имя"]
                count = int(row["Кол-во"])

                salary = count * PRICE  # считаем заново

                stats[name] = stats.get(name, 0) + salary
                total_sum += salary

        except:
            continue

    text = "📊 Выплаты за месяц:\n\n"

    for name, money in stats.items():
        text += f"{name} — {money} ₽\n"

    text += f"\nИТОГО: {total_sum} ₽"

    await message.answer(text)


# --- ОБЩИЙ ОТЧЁТ ---
@dp.message(F.text == "/total")
async def total_month(message: Message):
    now = datetime.now()
    data = sheet.get_all_records()

    stats = {}

    for row in data:
        try:
            row_date = datetime.strptime(row["Дата"], "%d.%m.%Y")

            if row_date.month == now.month and row_date.year == now.year:
                name = row["Имя"]
                salary = int(row["ЗП"])

                stats[name] = stats.get(name, 0) + salary

        except:
            continue

    text = "📊 Выплаты за месяц:\n\n"
    total_sum = 0

    for name, money in stats.items():
        text += f"{name} — {money} ₽\n"
        total_sum += money

    text += f"\nИТОГО: {total_sum} ₽"

    await message.answer(text)


# --- Напоминание ---
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
        await wait_until(time(18, 0))

        for user_id in users:
            try:
                await bot.send_message(user_id, "⏰ Сдайте отчёт за сегодня")
            except:
                pass


# --- Запуск ---
async def main():
    print("Бот запущен 🚀")
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
