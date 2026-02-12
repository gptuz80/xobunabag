import asyncio
import time
import random
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telegram import Bot, Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import sqlite3
import os

# ============================================
# KONFIGURATSIYA
# ============================================
BOT_TOKEN = "8337176690:AAEIko_hVRHff206GTA38wiVeV0dyKha8Eo"
API_ID = 20464354
API_HASH = "c6fa656e333fd6c9d5b9867daf028ea1"
PHONE_NUMBER = None  # Telefon raqam /start dan keyin so'raladi

# Kanallar
TARGET_CHANNEL = "Obunachi_X"  # Buyurtmalar keladigan kanal

# Database
conn = sqlite3.connect('obunachi.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT,
    channel_name TEXT,
    channel_link TEXT,
    completed BOOLEAN DEFAULT 0,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS stats (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    total_tasks INTEGER DEFAULT 0,
    completed_tasks INTEGER DEFAULT 0,
    last_task_time DATETIME
)''')
conn.commit()

# Global o'zgaruvchilar
user_client = None
bot_client = None
user_states = {}  # {chat_id: state}
pending_sessions = {}  # {chat_id: {'phone': phone, 'client': client}}
is_working = False
work_start_time = None
flood_wait_until = None
current_task = None

# ============================================
# TELEGRAM BOT HANDLERLARI
# ============================================
async def start_command(update: Update, context: CallbackContext):
    chat_id = update.effective_user.id
    user_states[chat_id] = 'waiting_phone'
    
    await update.message.reply_text(
        "🤖 **Obunachi X Avtomatik Bot**\n\n"
        "Botni ishga tushirish uchun telefon raqamingizni yuboring:\n"
        "📱 **Namuna:** `+998901234567`\n\n"
        "⚠️ Bu raqam @Obunachi_X kanalidan buyurtmalarni bajarish uchun ishlatiladi."
    )

async def handle_phone(update: Update, context: CallbackContext):
    global PHONE_NUMBER, user_client
    
    chat_id = update.effective_user.id
    if user_states.get(chat_id) != 'waiting_phone':
        return
    
    phone = update.message.text.strip()
    if not phone.startswith('+'):
        phone = '+' + phone
    
    PHONE_NUMBER = phone
    await update.message.reply_text(f"📱 Telefon raqam qabul qilindi: `{phone}`\n\n🔄 Telegram'ga ulanish...")
    
    try:
        # Telethon client yaratish
        session_name = f"sessions/obunachi_{phone.replace('+', '')}"
        user_client = TelegramClient(session_name, API_ID, API_HASH)
        
        await user_client.connect()
        
        if not await user_client.is_user_authorized():
            # Kod so'rash
            sent_code = await user_client.send_code_request(phone)
            pending_sessions[chat_id] = {
                'phone': phone,
                'phone_code_hash': sent_code.phone_code_hash,
                'client': user_client
            }
            user_states[chat_id] = 'waiting_code'
            await update.message.reply_text(
                "📨 Telegram'dan kelgan **5 xonali kodni** yuboring:\n"
                "⚠️ Masalan: `12345`"
            )
        else:
            # Avtorizatsiya qilingan
            user_states[chat_id] = 'active'
            await update.message.reply_text(
                "✅ **Muvaffaqiyatli ulanish!**\n"
                "Sessiya mavjud, /start_work buyrug'ini bosing."
            )
            
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {str(e)}")
        user_states[chat_id] = 'waiting_phone'

async def handle_code(update: Update, context: CallbackContext):
    chat_id = update.effective_user.id
    if user_states.get(chat_id) != 'waiting_code':
        return
    
    code = update.message.text.strip()
    if not code.isdigit() or len(code) != 5:
        await update.message.reply_text("❌ Kod 5 xonali raqam bo'lishi kerak!")
        return
    
    if chat_id not in pending_sessions:
        await update.message.reply_text("❌ Session topilmadi. Qayta /start bosing.")
        user_states[chat_id] = 'waiting_phone'
        return
    
    session_data = pending_sessions[chat_id]
    client = session_data['client']
    
    try:
        await client.sign_in(
            phone=session_data['phone'],
            code=code,
            phone_code_hash=session_data['phone_code_hash']
        )
        
        user_states[chat_id] = 'active'
        del pending_sessions[chat_id]
        
        await update.message.reply_text(
            "✅ **Muvaffaqiyatli kirildi!**\n\n"
            "🔍 @Obunachi_X kanaliga ulanish...\n"
            "Iltimos, biroz kuting..."
        )
        
        # Kanalga ulanish
        try:
            await client(JoinChannelRequest(TARGET_CHANNEL))
            await update.message.reply_text("✅ @Obunachi_X kanaliga ulandi!")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Kanalga ulanishda xatolik: {str(e)}")
        
        await update.message.reply_text(
            "🚀 **Ishni boshlash uchun** /start_work\n"
            "📊 **Statistika uchun** /stats\n"
            "🛑 **To'xtatish uchun** /stop"
        )
        
    except SessionPasswordNeededError:
        user_states[chat_id] = 'waiting_password'
        await update.message.reply_text(
            "🔐 **2FA paroli kerak.**\n"
            "Telegram akkauntingizning 2 qadamli autentifikatsiya parolini yuboring:"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {str(e)}")
        user_states[chat_id] = 'waiting_phone'

async def handle_password(update: Update, context: CallbackContext):
    chat_id = update.effective_user.id
    if user_states.get(chat_id) != 'waiting_password':
        return
    
    password = update.message.text.strip()
    
    if chat_id not in pending_sessions:
        await update.message.reply_text("❌ Session topilmadi. Qayta /start bosing.")
        user_states[chat_id] = 'waiting_phone'
        return
    
    client = pending_sessions[chat_id]['client']
    
    try:
        await client.sign_in(password=password)
        
        user_states[chat_id] = 'active'
        del pending_sessions[chat_id]
        
        await update.message.reply_text("✅ **2FA paroli qabul qilindi!**")
        
        # Kanalga ulanish
        try:
            await client(JoinChannelRequest(TARGET_CHANNEL))
            await update.message.reply_text("✅ @Obunachi_X kanaliga ulandi!")
        except:
            pass
        
        await update.message.reply_text(
            "🚀 **Ishni boshlash uchun** /start_work\n"
            "📊 **Statistika uchun** /stats\n"
            "🛑 **To'xtatish uchun** /stop"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Noto'g'ri parol: {str(e)}")

async def start_work_command(update: Update, context: CallbackContext):
    global is_working, work_start_time
    
    chat_id = update.effective_user.id
    if user_states.get(chat_id) != 'active':
        await update.message.reply_text("❌ Avval /start orqali kirishingiz kerak!")
        return
    
    if is_working:
        await update.message.reply_text("⚠️ Bot allaqachon ishlamoqda!")
        return
    
    is_working = True
    work_start_time = datetime.now()
    
    await update.message.reply_text(
        "🚀 **Ish boshlandi!**\n\n"
        "🔍 @Obunachi_X kanali kuzatilmoqda...\n"
        "✅ Yangi buyurtma kelganda avtomatik bajariladi.\n"
        "⏱ Limit bo'lsa 1 soat kutadi.\n\n"
        "📊 /stats - Statistika\n"
        "🛑 /stop - To'xtatish"
    )
    
    # Ishni boshlash
    asyncio.create_task(auto_work_loop(chat_id, update))

async def stop_work_command(update: Update, context: CallbackContext):
    global is_working
    is_working = False
    
    await update.message.reply_text(
        "🛑 **Ish to'xtatildi!**\n"
        "Qayta boshlash uchun /start_work"
    )

async def stats_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    cursor.execute('''SELECT balance, total_tasks, completed_tasks FROM stats WHERE user_id = ?''', (user_id,))
    stats = cursor.fetchone()
    
    if not stats:
        balance = total = completed = 0
    else:
        balance, total, completed = stats
    
    work_status = "✅ Ishlayapti" if is_working else "❌ To'xtatilgan"
    
    await update.message.reply_text(
        f"📊 **STATISTIKA**\n\n"
        f"👤 User ID: `{user_id}`\n"
        f"🤖 Holat: {work_status}\n"
        f"💰 Balans: **{balance} P**\n"
        f"📝 Jami topshiriq: **{total}**\n"
        f"✅ Bajarilgan: **{completed}**\n"
        f"⏳ Bajarilmagan: **{total - completed}**\n\n"
        f"📈 **Umumiy stat:**\n"
        f"• Soatlik limit: 50\n"
        f"• Kutish vaqti: 1 soat"
    )

# ============================================
# ASOSIY AVTOMATLASHTIRILGAN ISH JARAYONI
# ============================================
async def auto_work_loop(chat_id, update):
    """Asosiy avtomatik ish tsikli"""
    global is_working, flood_wait_until, current_task
    
    while is_working:
        try:
            # Flood limitni tekshirish
            if flood_wait_until and datetime.now() < flood_wait_until:
                wait_time = (flood_wait_until - datetime.now()).total_seconds()
                print(f"⏳ Flood limit: {wait_time:.0f} soniya kutish...")
                
                # Har 10 daqiqada xabar yuborish
                if int(wait_time) % 600 == 0:
                    await update.effective_user.send_message(
                        f"⏳ **Flood limit:** {wait_time/60:.0f} daqiqa kutish kerak..."
                    )
                
                await asyncio.sleep(10)
                continue
            
            # Kanalda yangi xabarlarni tekshirish
            await check_and_do_tasks(chat_id, update)
            
            # Har safar tekshirgandan keyin biroz kutish
            await asyncio.sleep(random.randint(5, 15))
            
        except FloodWaitError as e:
            # Telegram flood limiti
            wait_seconds = e.seconds
            flood_wait_until = datetime.now() + timedelta(seconds=wait_seconds)
            
            hours = wait_seconds // 3600
            minutes = (wait_seconds % 3600) // 60
            
            await update.effective_user.send_message(
                f"⚠️ **Telegram limiti!**\n"
                f"⏳ {hours} soat {minutes} daqiqa kutish kerak.\n"
                f"🔄 Avtomatik davom etadi..."
            )
            
            await asyncio.sleep(wait_seconds)
            flood_wait_until = None
            
        except Exception as e:
            print(f"❌ Xatolik: {e}")
            await asyncio.sleep(30)

async def check_and_do_tasks(chat_id, update):
    """Kanalda yangi topshiriqlarni tekshirish va bajarish"""
    global user_client, current_task, is_working
    
    if not is_working or not user_client:
        return
    
    try:
        # Kanaldan so'nggi xabarlarni olish
        messages = await user_client.get_messages(TARGET_CHANNEL, limit=10)
        
        for message in messages:
            if not message.text and not message.buttons:
                continue
            
            message_text = message.text or ""
            message_id = message.id
            
            # BUYURTMA NI TEKSHIRISH
            if "ID Raqami:" in message_text and "Nomi:" in message_text and "JOIN CHANNEL" in message_text:
                
                # Topshiriq ID sini olish
                task_id = None
                channel_name = None
                channel_link = None
                
                lines = message_text.split('\n')
                for line in lines:
                    if "ID Raqami:" in line:
                        task_id = line.replace("ID Raqami:", "").strip()
                    elif "Nomi:" in line:
                        channel_name = line.replace("Nomi:", "").strip()
                    elif "Usernamesi:" in line:
                        username = line.replace("Usernamesi:", "").strip()
                        channel_link = f"https://t.me/{username.replace('@', '')}"
                
                # Bu topshiriq allaqachon bajarilganmi?
                cursor.execute('''SELECT completed FROM tasks WHERE task_id = ?''', (task_id,))
                existing = cursor.fetchone()
                
                if existing and existing[0]:
                    continue  # Bajarilgan
                
                current_task = {
                    'id': task_id,
                    'name': channel_name,
                    'link': channel_link,
                    'message': message
                }
                
                print(f"\n🔔 YANGI BUYURTMA TOPILDI!")
                print(f"   ID: {task_id}")
                print(f"   Kanal: {channel_name}")
                print(f"   Link: {channel_link}")
                
                # TOPSHIRIQNI BAJARISH
                await update.effective_user.send_message(
                    f"🔔 **Yangi buyurtma!**\n"
                    f"📌 ID: `{task_id}`\n"
                    f"📢 Kanal: {channel_name}\n"
                    f"🔗 Link: {channel_link}\n\n"
                    f"🔄 Obuna bo'linmoqda..."
                )
                
                # 1. KANALGA OBUNA BO'LISH
                success = False
                try:
                    if channel_link:
                        if "+" in channel_link or "joinchat" in channel_link:
                            invite_hash = channel_link.split("+")[-1]
                            await user_client(ImportChatInviteRequest(invite_hash))
                        else:
                            channel_username = channel_link.split("/")[-1]
                            await user_client(JoinChannelRequest(channel_username))
                        
                        print(f"   ✅ Obuna bo'lindi: {channel_name}")
                        success = True
                        
                except FloodWaitError as e:
                    raise e
                except Exception as e:
                    print(f"   ❌ Obuna bo'lishda xatolik: {e}")
                
                if success:
                    await asyncio.sleep(random.randint(2, 5))
                    
                    # 2. TASDIQLASH TUGMASINI BOSISH
                    try:
                        # Xabardagi tugmalarni topish
                        if message.buttons:
                            for row in message.buttons:
                                for button in row:
                                    button_text = getattr(button, 'text', '').lower()
                                    
                                    if "tasdiqlash" in button_text or "confirm" in button_text or "✅" in button_text:
                                        await button.click()
                                        print(f"   ✅ Tasdiqlash tugmasi bosildi")
                                        
                                        # Statistika yangilash
                                        cursor.execute('''INSERT OR IGNORE INTO stats (user_id) VALUES (?)''', (chat_id,))
                                        cursor.execute('''UPDATE stats SET 
                                                        balance = balance + 1,
                                                        total_tasks = total_tasks + 1,
                                                        completed_tasks = completed_tasks + 1,
                                                        last_task_time = CURRENT_TIMESTAMP
                                                        WHERE user_id = ?''', (chat_id,))
                                        
                                        cursor.execute('''INSERT INTO tasks (task_id, channel_name, channel_link, completed) 
                                                        VALUES (?, ?, ?, 1)''', (task_id, channel_name, channel_link))
                                        conn.commit()
                                        
                                        await update.effective_user.send_message(
                                            f"✅ **Buyurtma bajarildi!**\n"
                                            f"📌 ID: {task_id}\n"
                                            f"💰 +1 P balans!"
                                        )
                                        
                                        break
                                
                    except Exception as e:
                        print(f"   ❌ Tasdiqlash xatolik: {e}")
                
                # Flood limitni oldini olish
                await asyncio.sleep(random.randint(10, 20))
                
    except FloodWaitError as e:
        raise e
    except Exception as e:
        print(f"❌ Tekshirish xatolik: {e}")

# ============================================
# TELEGRAM BOTNI ISHGA TUSHIRISH
# ============================================
async def main():
    """Asosiy funksiya"""
    global bot_client
    
    print("=" * 50)
    print("🤖 Obunachi X Avtomatik Bot")
    print("=" * 50)
    
    # Sessions papkasini yaratish
    if not os.path.exists("sessions"):
        os.makedirs("sessions")
    
    # Telegram botni ishga tushirish
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Handlerlarni qo'shish
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("start_work", start_work_command))
    application.add_handler(CommandHandler("stop", stop_work_command))
    application.add_handler(CommandHandler("stats", stats_command))
    
    # Text handler
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        lambda u, c: asyncio.create_task(
            handle_phone(u, c) if user_states.get(u.effective_user.id) == 'waiting_phone'
            else (handle_code(u, c) if user_states.get(u.effective_user.id) == 'waiting_code'
                  else handle_password(u, c))
        )
    ))
    
    print(f"\n✅ Bot ishga tushdi!")
    print(f"🤖 Bot: @{(await application.bot.get_me()).username}")
    print(f"📢 Target kanal: @{TARGET_CHANNEL}")
    print("\n📋 Foydalanish:")
    print("1. Botga /start bosing")
    print("2. Telefon raqamingizni yuboring")
    print("3. Telegram kodini yuboring")
    print("4. /start_work - ishni boshlash")
    print("5. /stats - statistika")
    print("6. /stop - to'xtatish")
    print("=" * 50)
    
    # Botni ishga tushirish
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # To'xtatmasdan kutish
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 Bot to'xtatildi!")
    except Exception as e:
        print(f"\n❌ Xatolik: {e}")