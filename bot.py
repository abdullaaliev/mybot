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


# --- Старт ---
@dp.message(F.text == "/start")
async def start(message: Message):
    users.add(message.from_user.id)

    await message.answer(
        "👋 Привет!\n\n"
        "✂️ Напиши, сколько изделий ты изготовила сегодня.\n\n"
        "Пример: 25"
    )


# --- Запись ---
@dp.message(F.text)
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

    salary = count * 70

    await message.answer(
        f"✅ Принято: {count}\n💰 ЗП: {salary} ₽"
    )

    asyncio.create_task(write_to_sheet(today, name, username, count, salary))


async def write_to_sheet(date, name, username, count, salary):
    await asyncio.to_thread(
        sheet.append_row,
        [date, name, username, count, salary]
    )


# --- ЗАРПЛАТА ЗА МЕСЯЦ (исправлено) ---
@dp.message(F.text == "/month")
async def my_month(message: Message):
    user_name = message.from_user.full_name
    now = datetime.now()

    data = sheet.get_all_records()

    total_count = 0
    total_salary = 0

    for row in data:
        try:
            row_date = datetime.strptime(row["Дата"], "%d.%m.%Y")

            if (
                row["Имя"] == user_name and
                row_date.month == now.month and
                row_date.year == now.year
            ):
                total_count += int(row["Кол-во"])
                total_salary += int(row["ЗП"])

        except:
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
