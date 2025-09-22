import os
import re
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from flask import Flask
import threading

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN', '8257089548:AAG3hpoUToom6a71peYep-DBfgPiKU3wPGE')
RS_USERNAMES = [None, None, None]

app_flask = Flask(__name__)

@app_flask.route('/health')
def health():
    return 'OK'

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
    pattern = r'(@[a-zA-Z0-9_]{1,32}|t\.me/[a-zA-Z0-9_]{1,32}|https?://(www\.)?t\.me/[a-zA-Z0-9_]{1,32})'
    def replace_match(match):
        orig = match.group(0)
        index = [i for i, u in enumerate(new_usernames) if u is not None].pop(0) if any(u is not None for u in new_usernames) else 0
        new_user = new_usernames[index % len([u for u in new_usernames if u])]
        if not new_user:
            return orig
        if orig.startswith("@"):
            return f"@{new_user}"
        elif orig.lower().startswith("t.me/"):
            return f"t.me/{new_user}"
        else:
            return f"https://t.me/{new_user}"
    return re.sub(pattern, replace_match, text, flags=re.IGNORECASE)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        """🤖 Welcome to HINDI ANIME CHANNEL BOT

        ✅ How to use:
        1. Set usernames: /set_rs username1 username2 username3
        2. COPY-PASTE messages here
        3. Batch update: /batch_update @channelusername 50

        ❌ Don't forward, COPY-PASTE instead"""
    )

async def set_rs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global RS_USERNAMES
    if len(context.args) >= 1 and len(context.args) <= 3:
        RS_USERNAMES = [_normalize_username(u) for u in context.args[:3]]
        RS_USERNAMES += [None] * (3 - len(context.args))
        await update.message.reply_text(f"✅ RS set: @{RS_USERNAMES[0]}, @{RS_USERNAMES[1]}, @{RS_USERNAMES[2]}")
        logger.info(f"RS set to {RS_USERNAMES}")
    else:
        await update.message.reply_text("Usage: /set_rs username1 username2 username3 (up to 3)")

async def batch_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global RS_USERNAMES
    if not RS_USERNAMES[0]:
        await update.message.reply_text("❌ Please set RS usernames with /set_rs")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /batch_update @channelusername message_count")
        return
    channel = context.args[0].lstrip('@')
    try:
        total_count = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ message_count must be a number.")
        return
    if total_count > 2000:
        await update.message.reply_text("❌ Max 2000 messages.")
        return
    await update.message.reply_text(f"🔄 Starting batch update for @{channel} ({total_count} messages)...")
    try:
        chat = await context.bot.get_chat(channel)
        if not chat.permissions.can_edit_messages:
            await update.message.reply_text("❌ Bot needs edit rights.")
            return
        processed = 0
        edited = 0
        offset_id = 0
        batch_size = 100
        while processed < total_count:
            batch_count = min(batch_size, total_count - processed)
            messages = await context.bot.get_chat_history(channel, limit=batch_count, offset=offset_id)
            if not messages:
                break
            for msg in messages:
                processed += 1
                text = msg.text or msg.caption or ""
                new_text = replace_all_usernames(text, RS_USERNAMES)
                if new_text != text:
                    try:
                        if msg.text:
                            await context.bot.edit_message_text(chat_id=channel, message_id=msg.message_id, text=new_text)
                        elif msg.caption:
                            await context.bot.edit_message_caption(chat_id=channel, message_id=msg.message_id, caption=new_text)
                        edited += 1
                    except Exception as e:
                        logger.error(f"Edit failed: {e}")
                await asyncio.sleep(0.5)
            offset_id += batch_count
        await update.message.reply_text(f"✅ Done. Processed: {processed}, Edited: {edited}")
    except Exception as e:
        logger.error(f"Batch update failed: {e}")
        await update.message.reply_text(f"❌ Failed: {e}")

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if hasattr(msg, 'forward_date') and msg.forward_date:
        await msg.reply_text("❌ Don't forward, COPY-PASTE! Use /start")
        return
    text = msg.text or msg.caption or ""
    if not RS_USERNAMES[0] or not text.strip():
        return
    new_text = replace_all_usernames(text, RS_USERNAMES)
    if new_text != text:
        await msg.reply_text(new_text)

def run_bot():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("set_rs", set_rs))
    application.add_handler(CommandHandler("batch_update", batch_update))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_message))
    logger.info("Bot started (polling)...")
    application.run_polling(timeout=60)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=lambda: app_flask.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False))
    flask_thread.start()
    run_bot()
