import asyncio
import os
import json
from datetime import datetime, time, timedelta
from typing import Dict, Set

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- ENV ---
API_TOKEN = os.getenv("API_TOKEN")
if not API_TOKEN:
    raise ValueError("API_TOKEN не найден")

creds_raw = os.getenv("GOOGLE_CREDS")
if creds_raw is None:
    raise ValueError("GOOGLE_CREDS не найден")

# --- Google Sheets ---
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

creds_dict = json.loads(creds_raw)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)

client = gspread.authorize(creds)

spreadsheet = client.open("Отчет")
sheet = spreadsheet.sheet1

# --- Users sheet (верификация) ---
try:
    users_sheet = spreadsheet.worksheet("Users")
except:
    users_sheet = spreadsheet.add_worksheet(title="Users", rows=1000, cols=1)
    users_sheet.append_row(["UserID"])

# --- Bot ---
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- CONFIG ---
PRICE = 80
ADMIN_ID = 8482392419
ACCESS_CODE = "2818"
REMINDER_TIME = time(18, 0)

# --- STATE ---
user_daily_log: Dict[int, Dict] = {}
users: Set[int] = set()


# =========================
# 🔐 ВЕРИФИКАЦИЯ
# =========================
def is_verified(user_id: int) -> bool:
    try:
        data = users_sheet.get_all_values()
        return str(user_id) in [row[0] for row in data]
    except:
        return False


def add_verified(user_id: int):
    users_sheet.append_row([str(user_id)])


# =========================
# 🚀 СТАРТ
# =========================
@dp.message(F.text == "/start")
async def start(message: Message):
    if is_verified(message.from_user.id):
        await message.answer("👋 Привет! Введи количество изделий")
    else:
        await message.answer("🔐 Введи код доступа")


# =========================
# 📌 ID
# =========================
@dp.message(F.text == "/id")
async def get_id(message: Message):
    await message.answer(f"Твой ID: {message.from_user.id}")


# =========================
# 🔐 ВВОД КОДА И ДАННЫХ
# =========================
@dp.message(F.text & ~F.text.startswith("/"))
async def handle_input(message: Message):
    user_id = message.from_user.id

    # --- НЕ ВЕРИФИЦИРОВАН ---
    if not is_verified(user_id):
        if message.text == ACCESS_CODE:
            add_verified(user_id)
            users.add(user_id)
            await message.answer("✅ Доступ открыт! Теперь отправь число изделий")
        else:
            await message.answer("🔐 Введи код доступа")
        return

    # --- ОБРАБОТКА ЧИСЕЛ ---
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

    user_daily_log[user_id] = {"date": today, "count": count}

    salary = count * PRICE

    await message.answer(f"✅ Принято: {count}\n💰 ЗП: {salary} ₽")

    await asyncio.to_thread(
        sheet.append_row,
        [today, name, username, user_id, count, salary]
    )


# =========================
# 💰 МОЙ МЕСЯЦ
# =========================
@dp.message(F.text == "/month")
async def my_month(message: Message):
    if not is_verified(message.from_user.id):
        await message.answer("🔐 Введи код доступа")
        return

    user_id = str(message.from_user.id)
    now = datetime.now()

    data = await asyncio.to_thread(sheet.get_all_records)

    total_salary = 0
    total_count = 0

    for row in data:
        try:
            row_date = datetime.strptime(row["Дата"], "%d.%m.%Y")

            if (
                str(row["UserID"]) == user_id
                and row_date.month == now.month
                and row_date.year == now.year
            ):
                total_salary += int(row["ЗП"])
                total_count += int(row["Кол-во"])
        except:
            continue

    await message.answer(
        f"💰 За месяц:\n\n"
        f"Изделий: {total_count}\n"
        f"ЗП: {total_salary} ₽"
    )


# =========================
# 📊 ОБЩИЙ ОТЧЁТ
# =========================
@dp.message(F.text == "/total")
async def total_month(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет доступа")
        return

    now = datetime.now()
    data = await asyncio.to_thread(sheet.get_all_records)

    stats = {}
    total_sum = 0

    for row in data:
        try:
            row_date = datetime.strptime(row["Дата"], "%d.%m.%Y")

            if row_date.month == now.month and row_date.year == now.year:
                name = row["Имя"]
                salary = int(row["ЗП"])

                stats[name] = stats.get(name, 0) + salary
                total_sum += salary
        except:
            continue

    text = "📊 Выплаты за месяц:\n\n"
    for name, money in stats.items():
        text += f"{name} — {money} ₽\n"

    text += f"\nИТОГО: {total_sum} ₽"
    await message.answer(text)


# =========================
# 🏆 ТОП НЕДЕЛИ
# =========================
@dp.message(F.text == "/top")
async def top_week(message: Message):
    if not is_verified(message.from_user.id):
        await message.answer("🔐 Введи код доступа")
        return

    now = datetime.now()
    week_ago = now - timedelta(days=7)

    data = await asyncio.to_thread(sheet.get_all_records)

    stats = {}

    for row in data:
        try:
            row_date = datetime.strptime(row["Дата"], "%d.%m.%Y")

            if week_ago <= row_date <= now:
                name = row["Имя"]
                count = int(row["Кол-во"])
                stats[name] = stats.get(name, 0) + count
        except:
            continue

    sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)

    text = "🏆 ТОП за неделю:\n\n"
    for i, (name, count) in enumerate(sorted_stats[:10], 1):
        text += f"{i}. {name} — {count}\n"

    await message.answer(text)


# =========================
# ⏰ НАПОМИНАНИЕ
# =========================
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


# =========================
# 🚀 ЗАПУСК
# =========================
async def main():
    print("Бот запущен 🚀")
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
