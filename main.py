import logging
import re
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from flask import Flask
import threading
import os

# ============= Token setup =============
TOKEN = os.environ.get('BOT_TOKEN', '8257089548:AAG3hpoUToom6a71peYep-DBfgPiKU3wPGE')  # Environment variable থেকে নেওয়া

# ============= Global username store ============
RS_USERNAMES = [None, None, None]  # তিনটি ইউজারনেম স্টোর করা

# ============= Logging ==========================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============= Flask Setup =================
app = Flask(__name__)

@app.route('/health')
def health():
    return 'OK'  # UptimeRobot এটি দেখে বট রানিং বলে ধরবে

# ============= Helper functions =================
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
        index = usernames.index(match.group(0)) % len([u for u in new_usernames if u])
        new_user = next((u for u in new_usernames if u), None)
        if not new_user:
            return orig
        if orig.startswith("@"):
            return f"@{new_user}"
        elif orig.lower().startswith("t.me/"):
            return f"t.me/{new_user}"
        else:
            return f"https://t.me/{new_user}"
    usernames = re.findall(pattern, text, flags=re.IGNORECASE)
    if not usernames:
        return text
    return re.sub(pattern, replace_match, text, count=len(usernames), flags=re.IGNORECASE)

# ============= Commands =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = """🤖 Welcome to HINDI ANIME CHANNEL BOT

    ✅ How to use:
    1. First set your usernames: /set_rs username1 username2 username3
    2. Then COPY-PASTE (not forward) any message here
    3. For batch update in channel: /batch_update @channelusername 50 (last 50 messages)

    ❌ DON'T FORWARD MESSAGES
    ✅ COPY-PASTE INSTEAD"""
    await update.message.reply_text(welcome_text)

async def set_rs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global RS_USERNAMES
    if len(context.args) >= 1 and len(context.args) <= 3:
        RS_USERNAMES = [_normalize_username(u) for u in context.args[:3]]
        RS_USERNAMES += [None] * (3 - len(context.args))
        await update.message.reply_text(f"✅ RS usernames set: @{RS_USERNAMES[0]}, @{RS_USERNAMES[1]}, @{RS_USERNAMES[2]}")
        logger.info(f"RS usernames set to {RS_USERNAMES} by {update.effective_user.id}")
    else:
        await update.message.reply_text("Usage: /set_rs username1 username2 username3 (up to 3 usernames)")

async def batch_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global RS_USERNAMES
    if not RS_USERNAMES[0]:
        await update.message.reply_text("❌ Please set at least one username using /set_rs yourusername")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /batch_update @channelusername message_count (e.g., /batch_update @yourchannel 50)")
        return
    
    channel_username = context.args[0].lstrip('@')
    try:
        total_count = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ message_count must be a number (e.g., 50)")
        return
    
    if total_count > 2000:
        await update.message.reply_text("❌ Max 2000 messages at a time to avoid rate limits")
        return
    
    await update.message.reply_text(f"🔄 Starting batch update for @{channel_username} (total {total_count} messages in batches of 100)...")
    
    try:
        chat = await context.bot.get_chat(channel_username)
        channel_id = chat.id
        
        # Check bot permissions
        me = await context.bot.get_me()
        member = await context.bot.get_chat_member(channel_id, me.id)
        if member.status not in ("administrator", "creator") or not member.can_edit_messages:
            await update.message.reply_text("❌ Bot must be admin with edit rights in the channel.")
            return
        
        offset_id = 0
        batch_size = 100
        processed_count = 0
        edited_count = 0
        
        while processed_count < total_count:
            batch_count = min(batch_size, total_count - processed_count)
            messages = await context.bot.get_chat_history(
                channel_id, limit=batch_count, offset=offset_id
            )
            
            if not messages:
                break
                
            for msg in messages:
                processed_count += 1
                text = msg.text or msg.caption or ""
                if not text.strip():
                    continue
                
                new_text = replace_all_usernames(text, RS_USERNAMES)
                if new_text != text:
                    try:
                        if msg.text:
                            await context.bot.edit_message_text(chat_id=channel_id, message_id=msg.message_id, text=new_text)
                        elif msg.caption:
                            await context.bot.edit_message_caption(chat_id=channel_id, message_id=msg.message_id, caption=new_text)
                        edited_count += 1
                    except Exception as e:
                        logger.error(f"Edit failed for msg {msg.message_id}: {e}")
                await asyncio.sleep(1)  # Rate limit এড়াতে
            
            offset_id += batch_count
            await update.message.reply_text(f"✅ Processed batch: {processed_count}/{total_count} messages, edited {edited_count}.")
        
        await update.message.reply_text(f"✅ Batch update complete! Processed {processed_count} messages, edited {edited_count} in @{channel_username}.")
    except Exception as e:
        logger.error(f"Batch update failed: {e}")
        await update.message.reply_text(f"❌ Batch update failed: {str(e)}")

# ============= Message handlers =================
async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    
    if hasattr(msg, 'forward_date') and msg.forward_date:
        await msg.reply_text("❌ Please COPY-PASTE the message instead of forwarding!\n\nUse /start for instructions")
        return
    
    text = msg.text or msg.caption or ""
    
    if not RS_USERNAMES[0]:
        await msg.reply_text("❌ Please set at least one username using /set_rs yourusername")
        return
    
    if not text.strip():
        return
    
    new_text = replace_all_usernames(text, RS_USERNAMES)
    
    if new_text != text:
        try:
            if msg.text:
                await msg.reply_text(new_text)
            elif msg.caption:
                if msg.video:
                    await msg.reply_video(msg.video.file_id, caption=new_text)
                elif msg.photo:
                    await msg.reply_photo(msg.photo[-1].file_id, caption=new_text)
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

# ============= Run Bot and Flask =================
def run_bot():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("set_rs", set_rs))
    application.add_handler(CommandHandler("batch_update", batch_update))
    application.add_handler(MessageHandler(
        filters.TEXT | filters.PHOTO | filters.VIDEO | filters.AUDIO |
        filters.Document.ALL | filters.VOICE | filters.Sticker.ALL,
        process_message
    ))
    logger.info("🤖 Bot started (polling)...")
    application.run_polling(timeout=60)

if __name__ == '__main__':
    # Flask সার্ভার একটি থ্রেডে চালান
    flask_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)), debug=False))
    flask_thread.start()
    # বট চালান
    run_bot()
