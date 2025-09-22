import os
import re
import logging
import threading
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, ContextTypes, filters
from flask import Flask

# ========= Config =========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
RS_USERNAMES = [None, None, None]
START_MESSAGE = "👋 Hello! I'm ready."
START_PHOTO = None
ADMIN_ID = 6621572366

# ========= Logging =========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========= Flask =========
app = Flask(__name__)
@app.route("/health")
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
    pattern = r'@[a-zA-Z0-9_]{1,32}|https?://t\.me/[a-zA-Z0-9_]{1,32}|t\.me/[a-zA-Z0-9_]{1,32}'
    matches = re.findall(pattern, text, flags=re.IGNORECASE)
    if not matches:
        return text
    new_text = text
    for i, match in enumerate(matches[:3]):
        if i < len(new_usernames) and new_usernames[i]:
            username = new_usernames[i]
            if match.startswith('@'):
                new_text = new_text.replace(match, f"@{username}")
            else:
                new_text = new_text.replace(match, f"https://t.me/{username}")
    return new_text

# ========= States =========
RS_WAIT, START_WAIT, PHOTO_WAIT = range(3)

# ========= /start =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if START_PHOTO:
        await update.message.reply_photo(photo=START_PHOTO, caption=START_MESSAGE)
    else:
        await update.message.reply_text(START_MESSAGE)

# ========= /set_rs =========
async def setrs_start(update, context):
    await update.message.reply_text("✏️ Send 1–3 usernames separated by space:")
    return RS_WAIT

async def setrs_receive(update, context):
    global RS_USERNAMES
    usernames = update.message.text.split()[:3]
    RS_USERNAMES = [_normalize_username(u) for u in usernames] + [None]*(3-len(usernames))
    await update.message.reply_text(f"✅ RS usernames set: {RS_USERNAMES}")
    return ConversationHandler.END

# ========= /setstart =========
async def setstart_start(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only Admin can use this command.")
        return ConversationHandler.END
    await update.message.reply_text("✏️ Send the new start message text:")
    return START_WAIT

async def setstart_receive(update, context):
    global START_MESSAGE
    START_MESSAGE = update.message.text
    await update.message.reply_text("✅ Start message updated!")
    return ConversationHandler.END

# ========= /setphoto =========
async def setphoto_start(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only Admin can use this command.")
        return ConversationHandler.END
    await update.message.reply_text("📸 Send a photo or paste a link to set the start photo:")
    return PHOTO_WAIT

async def setphoto_receive(update, context):
    global START_PHOTO
    if update.message.photo:
        START_PHOTO = update.message.photo[-1].file_id
        await update.message.reply_text("✅ Start photo updated from upload!")
    elif update.message.text:
        START_PHOTO = update.message.text.strip()
        await update.message.reply_text("✅ Start photo updated from link!")
    else:
        await update.message.reply_text("⚠️ Invalid input. Send a photo or valid link.")
        return PHOTO_WAIT
    return ConversationHandler.END

# ========= Message handler =========
async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = msg.text or msg.caption or ""
    if not text.strip() or not RS_USERNAMES[0]:
        return

    new_text = replace_all_usernames(text, RS_USERNAMES)
    if new_text != text:
        try:
            if msg.text:
                await msg.reply_text(new_text)
            elif msg.photo:
                await msg.reply_photo(msg.photo[-1].file_id, caption=new_text)
            elif msg.video:
                await msg.reply_video(msg.video.file_id, caption=new_text)
            elif msg.document:
                await msg.reply_document(msg.document.file_id, caption=new_text)
            elif msg.audio:
                await msg.reply_audio(msg.audio.file_id, caption=new_text)
            elif msg.voice:
                await msg.reply_voice(msg.voice.file_id, caption=new_text)
        except Exception as e:
            logger.error(f"Reply failed: {e}")

# ========= Conversation Handlers =========
rs_conv = ConversationHandler(
    entry_points=[CommandHandler("set_rs", setrs_start)],
    states={RS_WAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, setrs_receive)]},
    fallbacks=[]
)

setstart_conv = ConversationHandler(
    entry_points=[CommandHandler("setstart", setstart_start)],
    states={START_WAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, setstart_receive)]},
    fallbacks=[]
)

setphoto_conv = ConversationHandler(
    entry_points=[CommandHandler("setphoto", setphoto_start)],
    states={PHOTO_WAIT: [MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), setphoto_receive)]},
    fallbacks=[]
)

# ========= Run Bot =========
def run_bot():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(rs_conv)
    application.add_handler(setstart_conv)
    application.add_handler(setphoto_conv)
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, process_message))
    logger.info("🤖 Bot started...")
    application.run_polling()

# ========= Main =========
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 10000))
    threading.Thread(target=lambda: Flask(__name__).run(host="0.0.0.0", port=PORT, debug=False)).start()
    run_bot()
