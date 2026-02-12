import asyncio
import os
import random
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes


BOT_TOKEN = "8337176690:AAEIko_hVRHff206GTA38wiVeV0dyKha8Eo"
API_ID = 20464354
API_HASH = "c6fa656e333fd6c9d5b9867daf028ea1"

TARGET_CHANNEL = "@Obunachi_X"

user_client = None
pending_login = {}


############################
# LOGIN FUNKSIYALAR
############################

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📱 Telefon raqamingizni yuboring (+998...)")
    

async def phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global user_client

    phone = update.message.text

    session = f"sessions/{phone}"

    user_client = TelegramClient(session, API_ID, API_HASH)
    await user_client.connect()

    code = await user_client.send_code_request(phone)

    pending_login[update.effective_user.id] = {
        "phone": phone,
        "hash": code.phone_code_hash
    }

    await update.message.reply_text("📨 Telegramdan kelgan kodni yuboring.")


async def code_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    data = pending_login.get(update.effective_user.id)

    if not data:
        return

    try:
        await user_client.sign_in(
            phone=data["phone"],
            code=update.message.text,
            phone_code_hash=data["hash"]
        )

        await update.message.reply_text("✅ LOGIN BO‘LDI!")

        asyncio.create_task(start_userbot())

    except SessionPasswordNeededError:
        await update.message.reply_text("🔐 2FA parolni yuboring:")
        pending_login[update.effective_user.id]["2fa"] = True


async def password_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:
        await user_client.sign_in(password=update.message.text)

        await update.message.reply_text("✅ LOGIN BO‘LDI!")

        asyncio.create_task(start_userbot())

    except Exception as e:
        await update.message.reply_text(f"Xato: {e}")


############################
# JOIN FUNKSIYA
############################

async def join_channel(url):

    try:

        if "t.me/+" in url or "joinchat" in url:
            invite_hash = url.split("/")[-1].replace("+","")
            await user_client(ImportChatInviteRequest(invite_hash))

        else:
            username = url.split("/")[-1]
            entity = await user_client.get_entity(username)
            await user_client(JoinChannelRequest(entity))

        print("✅ REAL JOIN")

        await asyncio.sleep(random.randint(3,6))

        return True

    except FloodWaitError as e:
        print("Flood:", e.seconds)
        await asyncio.sleep(e.seconds)
        return False

    except Exception as e:
        print("JOIN ERROR:", e)
        return False


############################
# AUTO TASK
############################

async def start_userbot():

    @user_client.on(events.NewMessage(chats=TARGET_CHANNEL))
    async def handler(event):

        msg = event.message

        if not msg.buttons:
            return

        joined = False

        for row in msg.buttons:
            for btn in row:

                text = btn.text.lower()

                # JOIN
                if btn.url and ("join" in text or "kanal" in text):
                    joined = await join_channel(btn.url)

                # CONFIRM
                if joined and ("tasdiqlash" in text or "confirm" in text):
                    try:
                        await asyncio.sleep(random.randint(2,5))
                        await btn.click()
                        print("✅ CONFIRM BOSILDI")

                    except Exception as e:
                        print("CONFIRM ERROR:", e)

    print("🔥 USERBOT ISHLAYAPTI!")

    await user_client.run_until_disconnected()


############################
# MAIN
############################

async def main():

    if not os.path.exists("sessions"):
        os.makedirs("sessions")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex(r'^\+\d+'), phone_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, code_handler))

    print("🤖 BOT ISHLADI")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    await asyncio.Event().wait()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

