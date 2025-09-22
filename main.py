import os
import re
import asyncio
import logging
import threading
from flask import Flask
from pyrogram import Client, filters

# ================= Logging ===================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= Config ===================
API_ID = int(os.environ.get("API_ID", 25976192))  
API_HASH = os.environ.get("API_HASH", "8ba23141980539b4896e5adbc4ffd2e2")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

RS_USERNAMES = [None, None, None]  # replace usernames

# ================= Flask ===================
app = Flask(__name__)

@app.route("/health")
def health():
    return "OK"

# ================= Helper ===================
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
    replaced_count = 0
    def replacer(match):
        nonlocal replaced_count
        replacement = new_usernames[replaced_count % len(new_usernames)]
        replaced_count += 1
        if match.group(0).startswith('@'):
            return f"@{replacement}"
        elif match.group(0).startswith('t.me/'):
            return f"t.me/{replacement}"
        else:
            return f"https://t.me/{replacement}"
    return re.sub(
        r'@[a-zA-Z0-9_]{1,32}|t\.me/[a-zA-Z0-9_]{1,32}|https?://(www\.)?t\.me/[a-zA-Z0-9_]{1,32}',
        replacer, text, flags=re.IGNORECASE
    )

# ================= Pyrogram Client ===================
app_bot = Client(
    "RSBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# ================= Commands ===================
@app_bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    await message.reply(
        "🤖 HINDI ANIME CHANNEL BOT\n\n"
        "✅ /set_rs username1 username2 username3\n"
        "✅ Forward or copy messages to replace usernames\n"
        "✅ /batch_update @channelusername 5000 (Bot's own messages only)"
    )

@app_bot.on_message(filters.command("set_rs") & filters.private)
async def set_rs_cmd(client, message):
    global RS_USERNAMES
    args = message.text.split()[1:]
    if 1 <= len(args) <= 3:
        RS_USERNAMES = [_normalize_username(u) for u in args[:3]]
        RS_USERNAMES += [None]*(3-len(args))
        await message.reply(f"✅ RS usernames set: @{RS_USERNAMES[0]}, @{RS_USERNAMES[1]}, @{RS_USERNAMES[2]}")
    else:
        await message.reply("Usage: /set_rs username1 username2 username3")

# ================= Batch Update ===================
@app_bot.on_message(filters.command("batch_update") & filters.private)
async def batch_update_cmd(client, message):
    global RS_USERNAMES
    if not RS_USERNAMES[0]:
        await message.reply("❌ Set at least one username using /set_rs first")
        return
    args = message.text.split()[1:]
    if len(args) < 2:
        await message.reply("Usage: /batch_update @channelusername message_count")
        return

    channel_username = args[0].lstrip("@")
    try:
        total_count = int(args[1])
    except:
        await message.reply("❌ message_count must be a number")
        return

    await message.reply(f"🔄 Starting batch update @{channel_username} ({total_count} messages)")

    try:
        processed = 0
        async for msg in app_bot.iter_chat_history(channel_username, limit=total_count):
            # Only edit messages sent by this Bot
            if msg.from_user and msg.from_user.is_self:
                text = msg.text or msg.caption or ""
                if not text:
                    continue
                new_text = replace_all_usernames(text, RS_USERNAMES)
                try:
                    if msg.text:
                        await app_bot.edit_message_text(chat_id=msg.chat.id, message_id=msg.message_id, text=new_text)
                    elif msg.caption:
                        await app_bot.edit_message_caption(chat_id=msg.chat.id, message_id=msg.message_id, caption=new_text)
                    processed += 1
                    if processed % 50 == 0:
                        await asyncio.sleep(1)  # small pause every 50 messages
                except Exception as e:
                    logger.error(f"Edit failed for message {msg.message_id}: {e}")
        await message.reply(f"✅ Batch update complete! {processed}/{total_count} messages edited.")
    except Exception as e:
        await message.reply(f"❌ Batch update failed: {e}")

# ================= Forward / Normal Message Handler ===================
@app_bot.on_message(filters.private | filters.group)
async def handle_messages(client, message):
    text = message.text or message.caption or ""
    if not text and not message.photo and not message.video and not message.document:
        return
    if not RS_USERNAMES[0]:
        await message.reply("❌ Set at least one username using /set_rs first")
        return
    new_text = replace_all_usernames(text, RS_USERNAMES)
    try:
        if message.text:
            await message.reply(new_text)
        elif message.caption:
            if message.photo:
                await message.reply_photo(message.photo.file_id, caption=new_text)
            elif message.video:
                await message.reply_video(message.video.file_id, caption=new_text)
            elif message.document:
                await message.reply_document(message.document.file_id, caption=new_text)
            elif message.audio:
                await message.reply_audio(message.audio.file_id, caption=new_text)
            elif message.voice:
                await message.reply_voice(message.voice.file_id, caption=new_text)
            elif message.sticker:
                await message.reply_sticker(message.sticker.file_id)
    except Exception as e:
        logger.error(f"Repost failed: {e}")
        await message.reply(f"📝 Text version:\n\n{new_text}")

# ================= Run Flask & Bot ===================
def run_flask():
    PORT = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=PORT, debug=False)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    app_bot.run()
