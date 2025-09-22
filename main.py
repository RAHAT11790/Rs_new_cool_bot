import os
import re
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from flask import Flask
import threading

# ========= Config =========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

RS_USERNAMES = [None, None, None]   # ইউজারনেম স্টোর
FORCE_SUB_CHANNEL = None            # Force Sub channel link
START_MESSAGE = "👋 হ্যালো! আমি প্রস্তুত।"
START_PHOTO = None

# ========= Logging =========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========= Flask Setup =========
app = Flask(__name__)

@app.route('/health')
def health():
    return "OK"

# ========= Helper =========
def _normalize_username(u: str) -> str:
    if not u:
        return u
    u = u.strip()
    if u.startswith("@"):
        return u[1:]
    u = re.sub(r"^https?://(www\.)?t\.me/", "", u, flags=re.IGNORECASE)
    u = re.sub(r"^t\.me/", "", u, flags=re.IGNORECASE)
    return u

def replace_all_usernames(text: str, new_usernames: list) -> str:
    if not text or not new_usernames or all(u is None for u in new_usernames):
        return text

    usernames = re.findall(r'@[a-zA-Z0-9_]{1,32}|t\.me/[a-zA-Z0-9_]{1,32}|https?://(www\.)?t\.me/[a-zA-Z0-9_]{1,32}', text, flags=re.IGNORECASE)
    if not usernames:
        return text

    new_text = text
    for i, username in enumerate(usernames[:3]):
        if i < len(new_usernames) and new_usernames[i]:
            if username.startswith('@'):
                new_text = new_text.replace(username, f'@{new_usernames[i]}')
            elif username.startswith('t.me/'):
                new_text = new_text.replace(username, f't.me/{new_usernames[i]}')
            else:
                new_text = new_text.replace(username, f'https://t.me/{new_usernames[i]}')

    return new_text

# ========= Commands =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Force Subscribe check
    if FORCE_SUB_CHANNEL:
        try:
            channel_username = FORCE_SUB_CHANNEL.split("t.me/")[-1].replace("/", "")
            member = await context.bot.get_chat_member(f"@{channel_username}", user.id)

            if member.status in ["left", "kicked"]:
                keyboard = [[InlineKeyboardButton("✅ Join Channel", url=FORCE_SUB_CHANNEL)]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text("❌ প্রথমে আমাদের চ্যানেলে Join করুন তারপর Bot ব্যবহার করুন।", reply_markup=reply_markup)
                return
        except Exception:
            await update.message.reply_text("⚠️ Force Subscribe সঠিকভাবে সেট হয়নি।")
            return

    if START_PHOTO:
        await update.message.reply_photo(photo=START_PHOTO, caption=START_MESSAGE)
    else:
        await update.message.reply_text(START_MESSAGE)

async def set_rs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global RS_USERNAMES
    if len(context.args) >= 1 and len(context.args) <= 3:
        RS_USERNAMES = [_normalize_username(u) for u in context.args[:3]]
        RS_USERNAMES += [None] * (3 - len(context.args))
        await update.message.reply_text(f"✅ RS usernames set: {RS_USERNAMES}")
        logger.info(f"RS usernames set to {RS_USERNAMES} by {update.effective_user.id}")
    else:
        await update.message.reply_text("Usage: /set_rs username1 username2 username3 (up to 3)")

async def setstart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global START_MESSAGE
    if not context.args:
        await update.message.reply_text("Usage: /setstart [new start text]")
        return
    START_MESSAGE = " ".join(context.args)
    await update.message.reply_text("✅ Start message updated!")

async def setphoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global START_PHOTO
    if update.message.photo:
        START_PHOTO = update.message.photo[-1].file_id
        await update.message.reply_text("✅ Start photo updated from upload!")
    elif context.args:
        START_PHOTO = context.args[0]
        await update.message.reply_text("✅ Start photo updated from link!")
    else:
        await update.message.reply_text("Usage: /setphoto [send photo or paste link]")

async def forcesub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global FORCE_SUB_CHANNEL
    if not context.args:
        await update.message.reply_text("Usage: /forcesub https://t.me/YourChannel")
        return
    FORCE_SUB_CHANNEL = context.args[0]
    await update.message.reply_text(f"✅ Force Subscribe channel set: {FORCE_SUB_CHANNEL}")

# ========= Message Handler =========
async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if hasattr(msg, 'forward_date') and msg.forward_date:
        await msg.reply_text("❌ Forward করবেন না, COPY-PASTE করুন।")
        return

    text = msg.text or msg.caption or ""
    if not RS_USERNAMES[0]:
        return

    new_text = replace_all_usernames(text, RS_USERNAMES)
    if new_text != text:
        if msg.text:
            await msg.reply_text(new_text)
        elif msg.caption:
            if msg.photo:
                await msg.reply_photo(msg.photo[-1].file_id, caption=new_text)
            elif msg.video:
                await msg.reply_video(msg.video.file_id, caption=new_text)
            elif msg.document:
                await msg.reply_document(msg.document.file_id, caption=new_text)
            else:
                await msg.reply_text(new_text)

# ========= Run =========
def run_bot():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("set_rs", set_rs))
    application.add_handler(CommandHandler("setstart", setstart))
    application.add_handler(CommandHandler("setphoto", setphoto))
    application.add_handler(CommandHandler("forcesub", forcesub))
    application.add_handler(MessageHandler(
        filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL,
        process_message
    ))

    logger.info("🤖 Bot started...")
    application.run_polling()

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 10000))
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=PORT, debug=False)).start()
    run_bot()
