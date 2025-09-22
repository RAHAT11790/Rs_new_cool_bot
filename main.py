import logging
import re
import asyncio
import os
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# ================= Logging ===================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= BOT TOKEN ===================
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    logger.warning("❌ BOT_TOKEN environment variable not set! Please add it in Render Secrets.")
    TOKEN = None  # safe fallback

# ================= Username storage ===================
RS_USERNAMES = [None, None, None]

# ================= Flask setup ===================
app = Flask(__name__)

@app.route('/health')
def health():
    return "OK"

# ================= Helper functions ===================
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
    usernames = re.findall(
        r'@[a-zA-Z0-9_]{1,32}|t\.me/[a-zA-Z0-9_]{1,32}|https?://(www\.)?t\.me/[a-zA-Z0-9_]{1,32}',
        text, flags=re.IGNORECASE
    )
    if not usernames:
        return text

    def replacer(match):
        index = usernames.index(match.group(0)) % len(new_usernames)
        replacement = new_usernames[index]
        if match.group(0).startswith('@'):
            return f"@{replacement}"
        elif match.group(0).startswith('t.me/'):
            return f"t.me/{replacement}"
        else:
            return f"https://t.me/{replacement}"

    text = re.sub(
        r'@[a-zA-Z0-9_]{1,32}|t\.me/[a-zA-Z0-9_]{1,32}|https?://(www\.)?t\.me/[a-zA-Z0-9_]{1,32}',
        replacer, text, flags=re.IGNORECASE
    )
    return text

# ================= Commands ===================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Welcome to HINDI ANIME CHANNEL BOT\n\n"
        "✅ How to use:\n"
        "1. Set usernames: /set_rs username1 username2 username3\n"
        "2. COPY-PASTE messages here (not forward)\n"
        "3. Batch update in channel: /batch_update @channelusername 50"
    )

async def set_rs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global RS_USERNAMES
    if 1 <= len(context.args) <= 3:
        RS_USERNAMES = [_normalize_username(u) for u in context.args[:3]]
        RS_USERNAMES += [None] * (3 - len(context.args))
        await update.message.reply_text(
            f"✅ RS usernames set: @{RS_USERNAMES[0]}, @{RS_USERNAMES[1]}, @{RS_USERNAMES[2]}"
        )
    else:
        await update.message.reply_text("Usage: /set_rs username1 username2 username3 (up to 3 usernames)")

# ================= Message Handler ===================
async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = msg.text or msg.caption or ""

    if not RS_USERNAMES[0]:
        await msg.reply_text("❌ Please set at least one username using /set_rs")
        return

    if not text.strip() and not msg.photo and not msg.video and not msg.document:
        return

    # Username replace
    new_text = replace_all_usernames(text, RS_USERNAMES)

    try:
        # Forwarded message detection
        if msg.forward_from or msg.forward_from_chat:
            # Forwarded → username replace + reply/repost
            if msg.text:
                await msg.reply_text(new_text)
            elif msg.caption:
                if msg.photo:
                    await msg.reply_photo(msg.photo[-1].file_id, caption=new_text)
                elif msg.video:
                    await msg.reply_video(msg.video.file_id, caption=new_text)
                elif msg.document:
                    await msg.reply_document(msg.document.file_id, caption=new_text)
                elif msg.audio:
                    await msg.reply_audio(msg.audio.file_id, caption=new_text)
                elif msg.voice:
                    await msg.reply_voice(msg.voice.file_id, caption=new_text)
                elif msg.sticker:
                    await msg.reply_sticker(msg.sticker.file_id)
            return

        # Normal copy/paste
        if msg.text:
            await msg.reply_text(new_text)
        elif msg.caption:
            if msg.photo:
                await msg.reply_photo(msg.photo[-1].file_id, caption=new_text)
            elif msg.video:
                await msg.reply_video(msg.video.file_id, caption=new_text)
            elif msg.document:
                await msg.reply_document(msg.document.file_id, caption=new_text)
            elif msg.audio:
                await msg.reply_audio(msg.audio.file_id, caption=new_text)
            elif msg.voice:
                await msg.reply_voice(msg.voice.file_id, caption=new_text)
            elif msg.sticker:
                await msg.reply_sticker(msg.sticker.file_id)
    except Exception as e:
        logger.error(f"Repost failed: {e}")
        await msg.reply_text(f"📝 Text version:\n\n{new_text}")

# ================= Run Bot and Flask ===================
def run_bot():
    if not TOKEN:
        logger.warning("Bot is not starting because BOT_TOKEN is missing. Set it in Environment and restart.")
        return

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("set_rs", set_rs))
    application.add_handler(MessageHandler(
        filters.TEXT | filters.PHOTO | filters.VIDEO | filters.AUDIO |
        filters.Document.ALL | filters.VOICE | filters.Sticker.ALL,
        process_message
    ))
    logger.info("🤖 Bot started (polling)...")
    application.run_polling(timeout=60)

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 10000))
    flask_thread = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=PORT, debug=False))
    flask_thread.start()
    run_bot()
