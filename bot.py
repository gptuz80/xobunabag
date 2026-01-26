import asyncio
import os
from telethon import TelegramClient, events
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import Message
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# =========================
# CONFIG
# =========================
BOT_TOKEN = "8573440155:AAG2oHadY9thbvfRIYpIBMPcwhL9iw_hVL4"
API_ID = 20464354
API_HASH = "c6fa656e333fd6c9d5b9867daf028ea1"
BOT_USERNAME = "XObunachiBot"  # monitor qilinadigan bot

# Global state
client: TelegramClient | None = None
user_states = {}       # {user_id: 'waiting_phone' | 'waiting_code' | 'waiting_password' | 'active'}
pending_sessions = {}  # {user_id: {'phone': phone, 'code_hash': code_hash}}

# =========================
# TELETHON
# =========================
def create_telethon_client(phone: str):
    os.makedirs("sessions", exist_ok=True)
    session_name = f"sessions/session_{phone.replace('+', '')}"
    return TelegramClient(session_name, API_ID, API_HASH)


async def click_buttons(message: Message):
    """Telethon message ichidagi tugmalarni bosadi"""
    results = []

    if not message.buttons:
        return results

    for row in message.buttons:
        for button in row:
            # URL tugma
            url = getattr(button, "url", None)
            if url:
                try:
                    if "joinchat" in url or "+".encode() or "+" in url:
                        invite_hash = url.split("+")[-1]
                        await client(ImportChatInviteRequest(invite_hash))
                        results.append(f"✅ Invite orqali obuna bo'ldi: {url}")
                    else:
                        kanal = url.split("/")[-1]
                        await client(JoinChannelRequest(kanal))
                        results.append(f"✅ Kanalga obuna bo'ldi: {kanal}")
                except Exception as e:
                    results.append(f"⚠️ Obuna bo'lmadi: {e}")

            # Callback tugma (bosish)
            data = getattr(button, "data", None)
            if data:
                try:
                    await button.click()
                    results.append("✅ Tasdiqlash tugmasi bosildi")
                except Exception as e:
                    results.append(f"⚠️ Tasdiqlash tugmasi ishlamadi: {e}")

    return results


async def start_auto_subscribe(user_id: int, app: Application):
    """@Obunachi_X dan kelgan xabarlarda avtomatik tugma bosadi"""

    @client.on(events.NewMessage(chats=BOT_USERNAME))
    async def handler(event):
        try:
            results = await click_buttons(event.message)

            if results:
                msg = "<b>📋 Obuna natijalari:</b>\n\n" + "\n".join(results[:8])
                if len(results) > 8:
                    msg += f"\n\n...va yana {len(results) - 8} ta"

                try:
                    await app.bot.send_message(
                        chat_id=user_id,
                        text=msg,
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

        except Exception as e:
            print("Handler error:", e)


# =========================
# BOT HANDLERS
# =========================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_states[user_id] = "waiting_phone"

    await update.message.reply_text(
        "👋 <b>Obunachi Botiga xush kelibsiz!</b>\n\n"
        "Botni ishga tushirish uchun telefon raqamingizni yuboring:\n"
        "<b>Namuna:</b> <code>+998901234567</code>\n\n"
        "⚠️ <b>Diqqat:</b> Bu raqam kanallarga obuna bo'lish uchun ishlatiladi.",
        parse_mode="HTML"
    )


async def handle_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_states.get(user_id) != "waiting_phone":
        return

    phone = update.message.text.strip()
    if not phone.startswith("+"):
        phone = "+" + phone

    await update.message.reply_text(
        f"📱 <b>Telefon raqam qabul qilindi:</b> <code>{phone}</code>\n"
        f"Kod so'ralmoqda...",
        parse_mode="HTML"
    )

    global client
    try:
        client = create_telethon_client(phone)
        await client.connect()

        sent_code = await client.send_code_request(phone)
        code_hash = sent_code.phone_code_hash

        pending_sessions[user_id] = {"phone": phone, "code_hash": code_hash}
        user_states[user_id] = "waiting_code"

        await update.message.reply_text(
            "📨 Telegram'dan kelgan <b>5 xonali kodni</b> yuboring:\n\n"
            "⚠️ <b>Format:</b> <code>12345</code>",
            parse_mode="HTML"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {str(e)}")
        user_states[user_id] = "waiting_phone"


async def handle_auth_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_states.get(user_id) != "waiting_code":
        return

    code = update.message.text.strip()

    if not code.isdigit() or len(code) != 5:
        await update.message.reply_text("❌ <b>Kod 5 xonali raqam bo'lishi kerak!</b>", parse_mode="HTML")
        return

    await update.message.reply_text("🔐 <b>Kod tekshirilmoqda...</b>", parse_mode="HTML")

    if user_id not in pending_sessions:
        await update.message.reply_text("❌ Session topilmadi. Qayta /start bosing.")
        user_states[user_id] = "waiting_phone"
        return

    session_data = pending_sessions[user_id]
    phone = session_data["phone"]
    code_hash = session_data["code_hash"]

    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=code_hash)

        user_states[user_id] = "active"
        pending_sessions.pop(user_id, None)

        await update.message.reply_text(
            "✅ <b>Muvaffaqiyatli kirildi!</b>\n"
            "Endi /menu buyrug'i orqali ishni boshlashingiz mumkin.\n\n"
            "🤖 Bot endi <b>@Obunachi_X</b> dan xabarlarni kuzatib, avtomatik obuna bo'ladi.",
            parse_mode="HTML"
        )

        # monitor botga join (agar kerak bo‘lsa)
        try:
            await client(JoinChannelRequest(BOT_USERNAME))
        except Exception:
            pass

        asyncio.create_task(start_auto_subscribe(user_id, context.application))

    except SessionPasswordNeededError:
        user_states[user_id] = "waiting_password"
        await update.message.reply_text(
            "🔐 <b>2FA paroli kerak.</b>\n"
            "Telegram akkauntingizning 2 qadamli autentifikatsiya parolini yuboring:\n\n"
            "⚠️ <b>Format:</b> <code>meningparol123</code>",
            parse_mode="HTML"
        )

    except PhoneCodeInvalidError:
        await update.message.reply_text("❌ <b>Noto'g'ri kod.</b> Qayta urinib ko'ring.", parse_mode="HTML")

    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {str(e)}")
        user_states[user_id] = "waiting_phone"


async def handle_2fa_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_states.get(user_id) != "waiting_password":
        return

    password = update.message.text.strip()
    await update.message.reply_text("🔒 <b>Parol tekshirilmoqda...</b>", parse_mode="HTML")

    if user_id not in pending_sessions:
        await update.message.reply_text("❌ Session topilmadi.")
        user_states[user_id] = "waiting_phone"
        return

    try:
        await client.sign_in(password=password)

        user_states[user_id] = "active"
        pending_sessions.pop(user_id, None)

        await update.message.reply_text(
            "✅ <b>2FA paroli qabul qilindi!</b>\n"
            "Endi /menu buyrug'i orqali ishni boshlashingiz mumkin.\n\n"
            "🤖 Bot endi <b>@Obunachi_X</b> dan xabarlarni kuzatib, avtomatik obuna bo'ladi.",
            parse_mode="HTML"
        )

        try:
            await client(JoinChannelRequest(BOT_USERNAME))
        except Exception:
            pass

        asyncio.create_task(start_auto_subscribe(user_id, context.application))

    except Exception as e:
        await update.message.reply_text(f"❌ Noto'g'ri parol. Qayta urinib ko'ring: {str(e)}")


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_states.get(user_id) != "active":
        await update.message.reply_text(
            "❌ <b>Avval telefon raqam orqali kirishingiz kerak!</b>\n"
            "/start bosib qayta urinib ko'ring.",
            parse_mode="HTML"
        )
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Obuna bo'ldim", callback_data="subscribe_now")],
        [InlineKeyboardButton("📊 Status", callback_data="check_status")],
        [InlineKeyboardButton("🛑 To'xtatish", callback_data="stop_auto")]
    ])

    await update.message.reply_text(
        "<b>📱 Obunachi Bot Menyusi</b>\n\n"
        "✅ <b>Holat:</b> Faol\n"
        f"🤖 <b>Bot:</b> @{BOT_USERNAME}\n"
        "🔗 <b>Avtomatik obuna:</b> Yoqilgan\n\n"
        "Quyidagi tugmalardan foydalaning:",
        parse_mode="HTML",
        reply_markup=keyboard
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    await query.answer()

    if data == "subscribe_now":
        if user_states.get(user_id) != "active":
            await query.edit_message_text("❌ Avval telefon raqam orqali kirishingiz kerak!")
            return

        try:
            msgs = await client.get_messages(BOT_USERNAME, limit=5)

            for msg in msgs:
                results = await click_buttons(msg)
                if results:
                    await query.edit_message_text(
                        "<b>✅ Obuna jarayoni:</b>\n\n" + "\n".join(results[:5]),
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔄 Yangilash", callback_data="subscribe_now")]
                        ])
                    )
                    return

            await query.edit_message_text(
                "❌ Hozircha obuna qiladigan xabar topilmadi.\n"
                f"Bot @{BOT_USERNAME} dan yangi xabar kutmoqda.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Qayta urinish", callback_data="subscribe_now")]
                ])
            )

        except Exception as e:
            await query.edit_message_text(f"❌ Xatolik: {str(e)}")

    elif data == "check_status":
        status = user_states.get(user_id, "not_started")
        status_text = {
            "waiting_phone": "📞 Telefon raqam kutilmoqda",
            "waiting_code": "🔐 Auth kodi kutilmoqda",
            "waiting_password": "🔒 2FA paroli kutilmoqda",
            "active": "✅ Session faol",
            "not_started": "❌ Session yo'q",
        }

        holat = status_text.get(status, "Noma'lum")
        auto = "✅ Yoqilgan" if status == "active" else "❌ O'chirilgan"

        await query.edit_message_text(
            "<b>📊 Bot Holati:</b>\n\n"
            f"👤 <b>Foydalanuvchi ID:</b> {user_id}\n"
            f"📱 <b>Holat:</b> {holat}\n"
            f"🤖 <b>Monitor bot:</b> @{BOT_USERNAME}\n"
            f"🔗 <b>Avtomatik obuna:</b> {auto}",
            parse_mode="HTML"
        )

    elif data == "stop_auto":
        user_states[user_id] = "waiting_phone"
        await query.edit_message_text(
            "🛑 <b>Avtomatik obuna to'xtatildi!</b>\n\n"
            "Qayta ishga tushirish uchun /start ni bosing.",
            parse_mode="HTML"
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>📖 Yordam:</b>\n\n"
        "1) /start - Botni ishga tushirish\n"
        "2) Telefon raqam yuborasiz\n"
        "3) Telegramdan kelgan 5 xonali kod yuborasiz\n"
        "4) Agar 2FA bo'lsa parol yuborasiz\n"
        "5) /menu - Menyu\n\n"
        f"🤖 Bot avtomatik @{BOT_USERNAME} dan xabarlarni kuzatadi",
        parse_mode="HTML"
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    status = user_states.get(user_id, "not_started")

    status_text = {
        "waiting_phone": "📞 Telefon raqam kutilmoqda",
        "waiting_code": "🔐 Auth kodi kutilmoqda",
        "waiting_password": "🔒 2FA paroli kutilmoqda",
        "active": "✅ Session faol",
        "not_started": "❌ Session yo'q",
    }

    await update.message.reply_text(
        f"📊 <b>Holat:</b> {status_text.get(status, \"Noma'lum\")}",
        parse_mode="HTML"
    )


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Matn kelsa -> state bo‘yicha qaysi handler ekanini tanlaydi
    async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        state = user_states.get(uid)

        if state == "waiting_phone":
            await handle_phone_number(update, context)
        elif state == "waiting_code":
            await handle_auth_code(update, context)
        elif state == "waiting_password":
            await handle_2fa_password(update, context)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    print("🤖 Bot ishga tushdi...")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
