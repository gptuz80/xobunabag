import asyncio
import sqlite3
import os
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message

# Environment variables dan ma'lumot olish
API_ID = int(os.environ.get("API_ID", "34781111"))
API_HASH = os.environ.get("API_HASH", "f8d801388904eba3bbc892123698c928")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8573440155:AAG2oHadY9thbvfRIYpIBMPcwhL9iw_hVL4")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7902540547"))

# SQLite bazasini sozlash
conn = sqlite3.connect('subbot.db', check_same_thread=False)
cursor = conn.cursor()

# Jadval yaratish
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    total_subscribed INTEGER DEFAULT 0
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS channels (
    channel_id TEXT PRIMARY KEY,
    channel_link TEXT,
    points INTEGER DEFAULT 1,
    active BOOLEAN DEFAULT 1
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS user_channels (
    user_id INTEGER,
    channel_id TEXT,
    subscribed BOOLEAN DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(user_id),
    FOREIGN KEY(channel_id) REFERENCES channels(channel_id)
)''')
conn.commit()

app = Client("sub_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Start komandasi
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    user_id = message.from_user.id
    
    # Foydalanuvchini bazaga qo'shish
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    
    await show_main_menu(client, message.chat.id, user_id)

async def show_main_menu(client, chat_id, user_id):
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    balance = result[0] if result else 0
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💡 Obuna bolidim", callback_data="check_sub")],
        [InlineKeyboardButton("📊 Statistika", callback_data="stats")],
        [InlineKeyboardButton("👥 Referal", callback_data="referral")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="back_main")]
    ])
    
    await client.send_message(
        chat_id,
        f"**X Obunachi [Bot]**\n\n"
        f"Balansingiz: **{balance} P**\n\n"
        f"Kanalga obuna bo'ling va «💡️ Obuna bolidim» tugmasini bosing.\n"
        f"Har bir kanalga obuna bo'lgangiz uchun 1 P beriladi.",
        reply_markup=keyboard
    )

# Kanallarni tekshirish va yangi kanal ko'rsatish
@app.on_callback_query(filters.regex("check_sub"))
async def check_subscription(client, callback_query):
    user_id = callback_query.from_user.id
    
    # Obuna bo'lmagan kanalni topish
    cursor.execute('''SELECT c.channel_id, c.channel_link 
                    FROM channels c 
                    LEFT JOIN user_channels uc ON c.channel_id = uc.channel_id AND uc.user_id = ?
                    WHERE c.active = 1 AND (uc.subscribed IS NULL OR uc.subscribed = 0)
                    LIMIT 1''', (user_id,))
    
    channel = cursor.fetchone()
    
    if not channel:
        await callback_query.answer("Barcha kanallarga obuna bo'lib bo'ldingiz!", show_alert=True)
        return
    
    channel_id, channel_link = channel
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Kanalga o'tish", url=channel_link)],
        [InlineKeyboardButton("✅ Obuna bolidim", callback_data=f"confirm_{channel_id}")]
    ])
    
    await callback_query.message.edit_text(
        f"**ID Raqami: {channel_id[:6]}**\n"
        f"**Kanal:** {channel_link}\n\n"
        f"Kanalga obuna bo'ling va «✅ Obuna bolidim» tugmasini bosing.\n"
        f"Kanalga obuna bo'lganingiz uchun 1 P beriladi.",
        reply_markup=keyboard
    )
    await callback_query.answer()

# Obunani tasdiqlash
@app.on_callback_query(filters.regex(r"confirm_"))
async def confirm_subscription(client, callback_query):
    user_id = callback_query.from_user.id
    channel_id = callback_query.data.split("_")[1]
    
    try:
        # Foydalanuvchi kanalga obuna ekanligini tekshirish
        user = await app.get_chat_member(channel_id, user_id)
        
        if user.status in ["member", "administrator", "creator"]:
            # Obunani bazaga yozish
            cursor.execute("INSERT OR REPLACE INTO user_channels (user_id, channel_id, subscribed) VALUES (?, ?, 1)",
                          (user_id, channel_id))
            
            # Balansni oshirish
            cursor.execute("UPDATE users SET balance = balance + 1, total_subscribed = total_subscribed + 1 WHERE user_id = ?",
                          (user_id,))
            conn.commit()
            
            await callback_query.answer("Obuna muvaffaqiyatli tasdiqlandi! +1 P", show_alert=True)
            await check_subscription(client, callback_query)
        else:
            await callback_query.answer("Siz hali kanalga obuna bo'lmagansiz!", show_alert=True)
            
    except Exception as e:
        await callback_query.answer("Xatolik yuz berdi. Iltimos, kanalga obuna bo'lganingizni tekshiring.", show_alert=True)

# Statistika
@app.on_callback_query(filters.regex("stats"))
async def show_stats(client, callback_query):
    user_id = callback_query.from_user.id
    
    cursor.execute("SELECT balance, total_subscribed FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    balance = result[0] if result else 0
    total_subs = result[1] if result else 0
    
    stats_text = (
        f"📊 **Statistika**\n\n"
        f"👤 User ID: `{user_id}`\n"
        f"💰 Balans: **{balance} P**\n"
        f"✅ Obuna bo'lgan kanallar: **{total_subs} ta**\n"
        f"📈 Umumiy obunachilar: **13,260**"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Orqaga", callback_data="back_main")]
    ])
    
    await callback_query.message.edit_text(stats_text, reply_markup=keyboard)
    await callback_query.answer()

# Referal bo'limi
@app.on_callback_query(filters.regex("referral"))
async def show_referral(client, callback_query):
    user_id = callback_query.from_user.id
    bot_username = (await app.get_me()).username
    referral_text = (
        f"👥 **Referal**\n\n"
        f"🔗 **Obuna bo'lish**\n"
        f"• Gurunga odam qo'shish\n"
        f"• Topshiriqlar\n"
        f"• Post ko'rish\n"
        f"• Bonus\n\n"
        f"Referal havolangiz: `https://t.me/{bot_username}?start=ref_{user_id}`"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Orqaga", callback_data="back_main")]
    ])
    
    await callback_query.message.edit_text(referral_text, reply_markup=keyboard)
    await callback_query.answer()

# Orqaga tugmasi
@app.on_callback_query(filters.regex("back_main"))
async def back_to_main(client, callback_query):
    await show_main_menu(client, callback_query.message.chat.id, callback_query.from_user.id)
    await callback_query.answer()

# ADMIN: Yangi kanal qo'shish
@app.on_message(filters.command("add_channel") & filters.user(ADMIN_ID))
async def add_channel(client, message: Message):
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.reply("Foydalanish: /add_channel <channel_link>")
            return
            
        channel_link = args[1]
        
        # Kanal ID sini olish
        try:
            chat = await app.get_chat(channel_link)
            channel_id = str(chat.id)
            
            cursor.execute("INSERT OR REPLACE INTO channels (channel_id, channel_link) VALUES (?, ?)",
                          (channel_id, channel_link))
            conn.commit()
            
            await message.reply(f"✅ Kanal qo'shildi!\nID: {channel_id}\nLink: {channel_link}")
        except Exception as e:
            await message.reply(f"Xatolik: {str(e)}")
            
    except Exception as e:
        await message.reply(f"Umumiy xatolik: {str(e)}")

# ADMIN: Kanallar ro'yxati
@app.on_message(filters.command("list_channels") & filters.user(ADMIN_ID))
async def list_channels(client, message: Message):
    cursor.execute("SELECT channel_id, channel_link, active FROM channels")
    channels = cursor.fetchall()
    
    if not channels:
        await message.reply("📂 Kanallar ro'yxati bo'sh")
        return
    
    text = "📋 **Kanallar ro'yxati:**\n\n"
    for chan_id, link, active in channels:
        status = "✅" if active else "❌"
        text += f"{status} {link}\nID: `{chan_id}`\n\n"
    
    await message.reply(text)

async def main():
    await app.start()
    print("Bot ishga tushdi...")
    await idle()
    await app.stop()

if __name__ == "__main__":
    app.run(main())