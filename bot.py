import os
import time
import asyncio
import aiosqlite
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=TOKEN)
dp = Dispatcher()

DB = "data.db"

# ---------- DB ----------
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            phone TEXT,
            verified INTEGER DEFAULT 0,
            last_post INTEGER DEFAULT 0
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            text TEXT,
            status TEXT,
            msg_id INTEGER,
            created_at TEXT,
            updated_at TEXT
        )
        """)
        await db.commit()

# ---------- UI ----------
def contact_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
        resize_keyboard=True
    )

def ad_keyboard(ad_id, owner):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Продано", callback_data=f"sold_{ad_id}_{owner}"),
            InlineKeyboardButton(text="🟢 В продаже", callback_data=f"active_{ad_id}_{owner}")
        ]
    ])

# ---------- USER CHECK ----------
async def is_verified(user_id):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT verified FROM users WHERE user_id=?", (user_id,))
        r = await cur.fetchone()
        return r and r[0] == 1

# ---------- CONTACT ----------
@dp.message(lambda m: m.contact is not None)
async def contact(msg: types.Message):
    if msg.contact.user_id != msg.from_user.id:
        return

    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        INSERT OR REPLACE INTO users (user_id, username, phone, verified)
        VALUES (?, ?, ?, 1)
        """, (msg.from_user.id, msg.from_user.username or "none", msg.contact.phone_number))
        await db.commit()

    await msg.answer("OK. Доступ открыт.")

# ---------- CREATE AD ----------
@dp.message()
async def create(msg: types.Message):
    if msg.text.startswith("/"):
        return

    if not await is_verified(msg.from_user.id):
        await msg.answer("Нужна верификация", reply_markup=contact_keyboard())
        return

    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("""
        INSERT INTO ads (user_id, text, status, created_at, updated_at)
        VALUES (?, ?, 'active', ?, ?)
        """, (msg.from_user.id, msg.text, datetime.now().isoformat(), datetime.now().isoformat()))
        ad_id = cur.lastrowid
        await db.commit()

    text = f"""📦 #{ad_id}

{msg.text}

Статус: В продаже
"""

    sent = await bot.send_message(CHANNEL_ID, text, reply_markup=ad_keyboard(ad_id, msg.from_user.id))

    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE ads SET msg_id=? WHERE id=?", (sent.message_id, ad_id))
        await db.commit()

# ---------- STATUS ----------
@dp.callback_query()
async def callback(call: types.CallbackQuery):
    data = call.data.split("_")
    action = data[0]
    ad_id = int(data[1])
    owner = int(data[2])

    if call.from_user.id != owner:
        return

    status = "🟢 В продаже"
    if action == "sold":
        status = "🔴 Продано"

    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT text, msg_id FROM ads WHERE id=?", (ad_id,))
        row = await cur.fetchone()

    if not row:
        return

    text, msg_id = row

    new_text = f"""📦 #{ad_id}

{text}

Статус: {status}
✏️ Обновлено: {datetime.now().strftime('%H:%M')}
"""

    await bot.edit_message_text(new_text, CHANNEL_ID, msg_id, reply_markup=ad_keyboard(ad_id, owner))
    await call.answer("OK")

# ---------- START ----------
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())