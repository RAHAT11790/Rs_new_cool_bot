import os
import re
import logging
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, ContextTypes, filters
from flask import Flask

# ========= Config =========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

RS_USERNAMES = [None, None, None]
FORCE_SUB_CHANNEL = None
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

# ========= States =========
RS_WAIT, FORCE_WAIT, START_WAIT, PHOTO_WAIT = range(4)

# ========= /start =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # ForceSub check
    if FORCE_SUB_CHANNEL:
        try:
            channel_username = FORCE_SUB_CHANNEL.split("t.me/")[-1].replace("/", "")
            member = await context.bot.get_chat_member(f"@{channel_username}", user.id)
            if member.status in ["left", "kicked"]:
                keyboard = [[InlineKeyboardButton("✅ Join Channel", url=FORCE_SUB_CHANNEL)]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "❌ First join our channel to use the bot.",
                    reply_markup=reply_markup
                )
                return
        except Exception:
            await update.message.reply_text("⚠️ Force Subscribe not set properly.")
            return

    # Show start message + photo
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

# ========= /forcesub =========
async def forcesub_start(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only Admin can use this command.")
        return ConversationHandler.END
    await update.message.reply_text("🔗 Send the channel link for Force Subscribe:")
    return FORCE_WAIT

async def forcesub_receive(update, context):
    global FORCE_SUB_CHANNEL
    FORCE_SUB_CHANNEL = update.message.text.strip()
    await update.message.reply_text(f"✅ Force Subscribe channel set: {FORCE_SUB_CHANNEL}")
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

# ========= Message Handler =========
async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if hasattr(msg, 'forward_date') and msg.forward_date:
        await msg.reply_text("❌ Forward না করে copy-paste করুন।")
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

# ========= Conversation Handlers =========
rs_conv = ConversationHandler(
    entry_points=[CommandHandler("set_rs", setrs_start)],
    states={RS_WAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, setrs_receive)]},
    fallbacks=[]
)

forcesub_conv = ConversationHandler(
    entry_points=[CommandHandler("forcesub", forcesub_start)],
    states={FORCE_WAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, forcesub_receive)]},
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
    application.add_handler(forcesub_conv)
    application.add_handler(setstart_conv)
    application.add_handler(setphoto_conv)
    application.add_handler(MessageHandler(
        filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL,
        process_message
    ))

    logger.info("🤖 Bot started...")
    application.run_polling()

# ========= Main =========
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 10000))
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=PORT, debug=False)).start()
    run_bot()
