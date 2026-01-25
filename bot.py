import asyncio
import sqlite3
import os
from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message

# Telegram hisob ma'lumotlari
API_ID = int(os.environ.get("API_ID", "34781111"))
API_HASH = os.environ.get("API_HASH", "f8d801388904eba3bbc892123698c928")
PHONE_NUMBER = os.environ.get("PHONE_NUMBER", "+8801842594487")  # Sizning telefon raqamingiz
SESSION_NAME = "user_session"

# Bot tokeni
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8573440155:AAG2oHadY9thbvfRIYpIBMPcwhL9iw_hVL4")

# User client (sizning hisobingiz orqali)
user_client = Client(
    name=SESSION_NAME,
    api_id=API_ID,
    api_hash=API_HASH,
    phone_number=PHONE_NUMBER
)

# Bot client
bot_client = Client(
    "obuna_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Database setup
conn = sqlite3.connect('obuna_bot.db', check_same_thread=False)
cursor = conn.cursor()

# Tables
cursor.execute('''CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_link TEXT,
    channel_id TEXT,
    points INTEGER DEFAULT 1,
    completed INTEGER DEFAULT 0,
    user_id INTEGER
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    balance INTEGER DEFAULT 0,
    total_tasks INTEGER DEFAULT 0,
    completed_tasks INTEGER DEFAULT 0
)''')
conn.commit()

# Store for current tasks
user_tasks = {}

async def join_channel(channel_link):
    """Kanalga obuna bo'lish"""
    try:
        # Get channel entity
        channel = await user_client.get_chat(channel_link)
        
        # Join channel
        await user_client.join_chat(channel_link)
        print(f"Obuna bo'lindi: {channel_link}")
        
        # Check if successfully joined
        member = await user_client.get_chat_member(channel.id, "me")
        if member.status in ["member", "administrator", "creator"]:
            return True, channel.id
        return False, None
        
    except Exception as e:
        print(f"Xatolik: {e}")
        return False, None

async def leave_channel(channel_id):
    """Kanaldan chiqish"""
    try:
        await user_client.leave_chat(channel_id)
        print(f"Kanaldan chiqildi: {channel_id}")
        return True
    except:
        return False

# Bot handlers
@bot_client.on_message()
async def handle_messages(client, message):
    if message.text and message.text.startswith('/start'):
        user_id = message.from_user.id
        username = message.from_user.username or ""
        
        # Save user to database
        cursor.execute('''INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)''', 
                      (user_id, username))
        cursor.execute('''UPDATE users SET username = ? WHERE user_id = ?''', 
                      (username, user_id))
        conn.commit()
        
        # Get user stats
        cursor.execute('''SELECT balance, total_tasks, completed_tasks FROM users WHERE user_id = ?''', 
                      (user_id,))
        stats = cursor.fetchone()
        balance = stats[0] if stats else 0
        total_tasks = stats[1] if stats else 0
        completed_tasks = stats[2] if stats else 0
        
        # Create task for user
        task_id = 574027
        task_name = "Waka_stock"
        task_total = 25
        task_done = 19
        task_username = "@waka_stock_org"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Kanalga o'tish", url="https://t.me/waka_stock_org")],
            [InlineKeyboardButton("😊 Obuna bolidim", callback_data="subscribe_confirm")]
        ])
        
        await message.reply(
            f"**X Obunachi [Bot]**\n"
            f"13 260 monthly users\n"
            f"\n---\n"
            f"**ID**\n"
            f"ID Raqami: {task_id}\n"
            f"**Nomi:** {task_name}\n"
            f"**Buyurtma soni:** {task_total}\n"
            f"**Bajarildi:** {task_done}\n"
            f"**Usernamesi:** {task_username}\n"
            f"\n---\n"
            f"Kanalga obuna bo'ling va 😊 Obuna bolidim\n"
            f"tugmasini bosing.\n"
            f"Kanalga obuna bo'lganingiz uchun 1 P beriladi\n"
            f"\n---\n"
            f"**Balans:** {balance} P\n"
            f"**Bajarilgan:** {completed_tasks}/{total_tasks}\n",
            reply_markup=keyboard
        )

@bot_client.on_callback_query()
async def handle_callbacks(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    if data == "subscribe_confirm":
        # Join channel using user account
        channel_link = "https://t.me/waka_stock_org"
        
        try:
            # Attempt to join channel
            success, channel_id = await join_channel(channel_link)
            
            if success:
                # Update user balance
                cursor.execute('''UPDATE users SET 
                                balance = balance + 1,
                                total_tasks = total_tasks + 1,
                                completed_tasks = completed_tasks + 1 
                                WHERE user_id = ?''', (user_id,))
                conn.commit()
                
                # Get updated stats
                cursor.execute('''SELECT balance, completed_tasks FROM users WHERE user_id = ?''', 
                             (user_id,))
                stats = cursor.fetchone()
                new_balance = stats[0] if stats else 1
                completed = stats[1] if stats else 1
                
                await callback_query.answer(
                    f"✅ Obuna bo'ldingiz! +1 P\n"
                    f"Yangı balans: {new_balance} P\n"
                    f"Bajarilgan: {completed} ta",
                    show_alert=True
                )
                
                # Create next task
                next_task_id = 574028
                next_task_name = "Next_Channel"
                next_task_total = 30
                next_task_done = completed + 1
                next_task_username = "@next_channel"
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 Kanalga o'tish", url="https://t.me/next_channel")],
                    [InlineKeyboardButton("😊 Obuna bolidim", callback_data="subscribe_next")]
                ])
                
                await callback_query.message.edit_text(
                    f"**X Obunachi [Bot]**\n"
                    f"13 260 monthly users\n"
                    f"\n---\n"
                    f"**ID**\n"
                    f"ID Raqami: {next_task_id}\n"
                    f"**Nomi:** {next_task_name}\n"
                    f"**Buyurtma soni:** {next_task_total}\n"
                    f"**Bajarildi:** {next_task_done}\n"
                    f"**Usernamesi:** {next_task_username}\n"
                    f"\n---\n"
                    f"Kanalga obuna bo'ling va 😊 Obuna bolidim\n"
                    f"tugmasini bosing.\n"
                    f"Kanalga obuna bo'lganingiz uchun 1 P beriladi\n"
                    f"\n---\n"
                    f"**Balans:** {new_balance} P\n"
                    f"**Bajarilgan:** {completed}/{next_task_total}\n",
                    reply_markup=keyboard
                )
                
                # Store task for next callback
                user_tasks[user_id] = {
                    "next_channel": "https://t.me/next_channel",
                    "task_number": next_task_id
                }
                
                # Auto-leave after some time (optional)
                # await asyncio.sleep(300)  # 5 minutes
                # await leave_channel(channel_id)
                
            else:
                await callback_query.answer(
                    "❌ Obuna bo'lishda xatolik. Qayta urinib ko'ring.",
                    show_alert=True
                )
                
        except Exception as e:
            await callback_query.answer(
                f"Xatolik: {str(e)}",
                show_alert=True
            )
    
    elif data == "subscribe_next":
        # Handle next subscription
        if user_id in user_tasks:
            channel_link = user_tasks[user_id]["next_channel"]
            success, _ = await join_channel(channel_link)
            
            if success:
                cursor.execute('''UPDATE users SET 
                                balance = balance + 1,
                                completed_tasks = completed_tasks + 1 
                                WHERE user_id = ?''', (user_id,))
                conn.commit()
                
                await callback_query.answer(
                    "✅ Keyingi kanalga obuna bo'ldingiz! +1 P",
                    show_alert=True
                )

async def main():
    # Start both clients
    print("User hisobini ishga tushiramiz...")
    await user_client.start()
    
    print("Botni ishga tushiramiz...")
    await bot_client.start()
    
    print("Bot ishga tushdi. @BotFather dan olingan bot token orqali botga kirishingiz mumkin.")
    
    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    # Create required directories
    if not os.path.exists("sessions"):
        os.makedirs("sessions")
    
    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot to'xtatildi.")