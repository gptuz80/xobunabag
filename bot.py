import asyncio
import time
import random
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import sqlite3
import os

# ============================================
# KONFIGURATSIYA
# ============================================
BOT_TOKEN = "8226329148:AAH6HwVuE9KAyMAkURH0KMVK3gpxChdHHw0"
API_ID = 20464354
API_HASH = "c6fa656e333fd6c9d5b9867daf028ea1"
PHONE_NUMBER = None

# Kanallar
TARGET_CHANNEL = "@Obunachi_X"

# Database
conn = sqlite3.connect('obunachi.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT UNIQUE,
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
user_states = {}  # {chat_id: state}
pending_sessions = {}  # {chat_id: {'phone': phone, 'client': client}}
is_working = False
flood_wait_until = None
processed_messages = set()  # Qayta ishlangan xabarlar ID si
last_task_time = None  # Oxirgi bajarilgan topshiriq vaqti
TASK_INTERVAL = 60  # Har 60 soniyada 1 ta topshiriq

# ============================================
# TELEGRAM BOT HANDLERLARI
# ============================================
async def start_command(update: Update, context: CallbackContext):
    chat_id = update.effective_user.id
    user_states[chat_id] = 'waiting_phone'
    
    await update.message.reply_text(
        "🤖 Obunachi X Avtomatik Bot\n\n"
        "Botni ishga tushirish uchun telefon raqamingizni yuboring:\n"
        "📱 Namuna: +998901234567\n\n"
        "⚠️ Bu raqam @Obunachi_X kanalidan buyurtmalarni bajarish uchun ishlatiladi."
    )

async def set_interval_command(update: Update, context: CallbackContext):
    global TASK_INTERVAL
    
    try:
        args = context.args
        if args and args[0].isdigit():
            new_interval = int(args[0])
            if 30 <= new_interval <= 300:  # 30 soniyadan 5 minutgacha
                TASK_INTERVAL = new_interval
                await update.message.reply_text(f"✅ Vaqt oralig'i {new_interval} soniyaga o'zgartirildi!")
            else:
                await update.message.reply_text("❌ Vaqt oralig'i 30-300 soniya orasida bo'lishi kerak!")
        else:
            await update.message.reply_text(f"⏱ Hozirgi vaqt oralig'i: {TASK_INTERVAL} soniya\n"
                                          f"/set_interval [soniya] - yangi vaqt oralig'ini belgilash")
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {e}")

async def handle_phone(update: Update, context: CallbackContext):
    global PHONE_NUMBER, user_client
    
    chat_id = update.effective_user.id
    if user_states.get(chat_id) != 'waiting_phone':
        return
    
    phone = update.message.text.strip()
    if not phone.startswith('+'):
        phone = '+' + phone
    
    PHONE_NUMBER = phone
    await update.message.reply_text(f"📱 Telefon raqam qabul qilindi: {phone}\n\n🔄 Telegram'ga ulanish...")
    
    try:
        session_name = f"sessions/obunachi_{phone.replace('+', '')}"
        user_client = TelegramClient(session_name, API_ID, API_HASH)
        
        await user_client.connect()
        
        if not await user_client.is_user_authorized():
            sent_code = await user_client.send_code_request(phone)
            pending_sessions[chat_id] = {
                'phone': phone,
                'phone_code_hash': sent_code.phone_code_hash,
                'client': user_client
            }
            user_states[chat_id] = 'waiting_code'
            await update.message.reply_text(
                "📨 Telegram'dan kelgan 5 xonali kodni yuboring:\n"
                "Masalan: 12345"
            )
        else:
            user_states[chat_id] = 'active'
            await update.message.reply_text(
                "✅ Muvaffaqiyatli ulanish!\n"
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
        
        await update.message.reply_text("✅ Muvaffaqiyatli kirildi!")
        
        # Kanalga ulanish
        try:
            await client(JoinChannelRequest(TARGET_CHANNEL))
            await update.message.reply_text("✅ @Obunachi_X kanaliga ulandi!")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Kanalga ulanishda xatolik: {str(e)}")
        
        await update.message.reply_text(
            "🚀 Ishni boshlash uchun /start_work\n"
            "📊 Statistika uchun /stats\n"
            "🛑 To'xtatish uchun /stop"
        )
        
    except SessionPasswordNeededError:
        user_states[chat_id] = 'waiting_password'
        await update.message.reply_text(
            "🔐 2FA paroli kerak.\n"
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
        
        await update.message.reply_text("✅ 2FA paroli qabul qilindi!")
        
        # Kanalga ulanish
        try:
            await client(JoinChannelRequest(TARGET_CHANNEL))
            await update.message.reply_text("✅ @Obunachi_X kanaliga ulandi!")
        except:
            pass
        
        await update.message.reply_text(
            "🚀 Ishni boshlash uchun /start_work\n"
            "📊 Statistika uchun /stats\n"
            "🛑 To'xtatish uchun /stop"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Noto'g'ri parol: {str(e)}")

async def start_work_command(update: Update, context: CallbackContext):
    global is_working, processed_messages, last_task_time
    
    chat_id = update.effective_user.id
    if user_states.get(chat_id) != 'active':
        await update.message.reply_text("❌ Avval /start orqali kirishingiz kerak!")
        return
    
    if is_working:
        await update.message.reply_text("⚠️ Bot allaqachon ishlamoqda!")
        return
    
    is_working = True
    processed_messages = set()  # Tozalash
    last_task_time = datetime.now()
    
    await update.message.reply_text(
        f"🚀 Ish boshlandi!\n\n"
        f"🔍 @Obunachi_X kanali kuzatilmoqda...\n"
        f"✅ Har {TASK_INTERVAL} soniyada 1 ta topshiriq bajariladi.\n\n"
        f"📊 /stats - Statistika\n"
        f"⏱ /set_interval - Vaqt oralig'ini o'zgartirish\n"
        f"🛑 /stop - To'xtatish"
    )
    
    # Ishni boshlash
    asyncio.create_task(auto_work_loop(chat_id, update))

async def stop_work_command(update: Update, context: CallbackContext):
    global is_working
    is_working = False
    
    await update.message.reply_text(
        "🛑 Ish to'xtatildi!\n"
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
        f"📊 STATISTIKA\n\n"
        f"👤 User ID: {user_id}\n"
        f"🤖 Holat: {work_status}\n"
        f"💰 Balans: {balance} P\n"
        f"📝 Jami topshiriq: {total}\n"
        f"✅ Bajarilgan: {completed}\n"
        f"⏳ Bajarilmagan: {total - completed}\n"
        f"⏱ Vaqt oralig'i: {TASK_INTERVAL} soniya"
    )

# ============================================
# ASOSIY AVTOMATLASHTIRILGAN ISH JARAYONI
# ============================================
async def auto_work_loop(chat_id, update):
    """Asosiy avtomatik ish tsikli"""
    global is_working, flood_wait_until, last_task_time
    
    while is_working:
        try:
            # Flood limitni tekshirish
            if flood_wait_until and datetime.now() < flood_wait_until:
                wait_time = (flood_wait_until - datetime.now()).total_seconds()
                await asyncio.sleep(10)
                continue
            
            # Vaqt oralig'ini tekshirish
            current_time = datetime.now()
            if last_task_time:
                time_diff = (current_time - last_task_time).total_seconds()
                if time_diff < TASK_INTERVAL:
                    # Hali vaqt to'lmagan bo'lsa, kutish
                    wait_seconds = TASK_INTERVAL - time_diff
                    if wait_seconds > 0:
                        print(f"⏳ {wait_seconds:.0f} soniya kutish...")
                        await asyncio.sleep(min(wait_seconds, 5))
                        continue
            
            # Kanalda yangi xabarlarni tekshirish
            task_done = await check_and_do_tasks(chat_id, update)
            
            if task_done:
                # Agar topshiriq bajarilgan bo'lsa, vaqtni yangilash
                last_task_time = datetime.now()
                print(f"✅ Topshiriq bajarildi! Keyingi topshiriq {TASK_INTERVAL} soniyadan keyin")
            
            # Har safar tekshirgandan keyin biroz kutish
            await asyncio.sleep(random.randint(2, 4))
            
        except FloodWaitError as e:
            wait_seconds = e.seconds
            flood_wait_until = datetime.now() + timedelta(seconds=wait_seconds)
            
            hours = wait_seconds // 3600
            minutes = (wait_seconds % 3600) // 60
            
            await update.effective_user.send_message(
                f"⚠️ Telegram limiti!\n"
                f"⏳ {hours} soat {minutes} daqiqa kutish kerak.\n"
                f"🔄 Avtomatik davom etadi..."
            )
            
            await asyncio.sleep(wait_seconds)
            flood_wait_until = None
            last_task_time = datetime.now()  # Limitdan keyin vaqtni reset qilish
            
        except Exception as e:
            print(f"❌ Xatolik: {e}")
            await asyncio.sleep(5)

async def join_channel(channel_url):
    """Kanalga obuna bo'lish"""
    try:
        if "t.me/+" in channel_url or "joinchat" in channel_url:
            # Private kanal
            invite_hash = channel_url.split("/")[-1].replace("+", "")
            await user_client(ImportChatInviteRequest(invite_hash))
        else:
            # Public kanal
            username = channel_url.split("/")[-1]
            await user_client(JoinChannelRequest(username))
        
        print(f"✅ Kanalga obuna bo'lindi: {channel_url}")
        return True
    except Exception as e:
        print(f"❌ Obuna xatoligi: {e}")
        return False

async def check_and_do_tasks(chat_id, update):
    """Kanalda yangi topshiriqlarni tekshirish va bajarish"""
    global user_client, is_working, processed_messages

    if not is_working or not user_client:
        return False

    try:
        # Oxirgi 5 xabarni olish
        messages = await user_client.get_messages(TARGET_CHANNEL, limit=5)

        for message in messages:
            message_id = message.id
            
            # Agar bu xabar allaqachon ishlangan bo'lsa, o'tkazib yubor
            if message_id in processed_messages:
                continue
            
            # Xabarda tugma bormi?
            if not message.buttons:
                continue
            
            print(f"\n📨 Yangi xabar topildi! ID: {message_id}")
            
            # Tugmalarni tekshirish
            join_clicked = False
            channel_link = None
            
            for row in message.buttons:
                for button in row:
                    button_text = button.text.lower()
                    
                    # Kanalga o'tish tugmasi (JOIN CHANNEL)
                    if ("join" in button_text or "kanal" in button_text) and hasattr(button, 'url') and button.url:
                        channel_link = button.url
                        print(f"🔗 Kanal topildi: {channel_link}")
                        
                        # Kanalga obuna bo'lish
                        success = await join_channel(channel_link)
                        
                        if success:
                            join_clicked = True
                            print(f"✅ Obuna bo'lindi!")
                            await asyncio.sleep(random.randint(2, 4))
                    
                    # Tasdiqlash tugmasi (faqat join bo'lgan bo'lsa)
                    if join_clicked and ("tasdiqlash" in button_text or "confirm" in button_text or "✅" in button.text):
                        try:
                            # Callback tugmani bosish
                            await button.click()
                            print(f"✅ Tasdiqlandi!")
                            
                            # Statistika yangilash
                            cursor.execute('''INSERT OR IGNORE INTO stats (user_id) VALUES (?)''', (chat_id,))
                            cursor.execute('''UPDATE stats SET 
                                            balance = balance + 1,
                                            total_tasks = total_tasks + 1,
                                            completed_tasks = completed_tasks + 1,
                                            last_task_time = CURRENT_TIMESTAMP
                                            WHERE user_id = ?''', (chat_id,))
                            
                            # Topshiriqni bazaga yozish
                            try:
                                cursor.execute('''INSERT OR IGNORE INTO tasks (task_id, channel_name, channel_link, completed) 
                                                VALUES (?, ?, ?, 1)''', 
                                                (str(message_id), "Unknown", channel_link or "unknown"))
                            except:
                                pass  # Duplicate bo'lsa ignore
                            
                            conn.commit()
                            
                            await update.effective_user.send_message(
                                f"✅ Buyurtma bajarildi! +1 balans"
                            )
                            
                            # Xabarni ishlangan deb belgilash
                            processed_messages.add(message_id)
                            
                            return True  # Topshiriq bajarildi
                            
                        except Exception as e:
                            print(f"❌ Tasdiqlash xatosi: {e}")
            
            # Agar join qilingan bo'lsa lekin tasdiqlash topilmagan bo'lsa
            if join_clicked:
                processed_messages.add(message_id)
                return True
                
    except FloodWaitError as e:
        raise e
    except Exception as e:
        print(f"❌ Task xatosi: {e}")
    
    return False  # Topshiriq bajarilmadi

# ============================================
# TELEGRAM BOTNI ISHGA TUSHIRISH
# ============================================
async def main():
    """Asosiy funksiya"""
    
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
    application.add_handler(CommandHandler("set_interval", set_interval_command))
    
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
    print(f"📢 Target kanal: {TARGET_CHANNEL}")
    print(f"⏱ Standart vaqt oralig'i: {TASK_INTERVAL} soniya")
    print("\n📋 Foydalanish:")
    print("1. Botga /start bosing")
    print("2. Telefon raqamingizni yuboring")
    print("3. Telegram kodini yuboring")
    print("4. /start_work - ishni boshlash")
    print("5. /set_interval 120 - vaqtni o'zgartirish")
    print("6. /stats - statistika")
    print("7. /stop - to'xtatish")
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