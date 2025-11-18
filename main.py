import os
import re
import base64
import logging
import asyncio
import time
import shutil
import platform
import tarfile
import tempfile
from typing import Dict, List

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import (
    UserAlreadyParticipant, ChatAdminRequired, UserNotParticipant, PeerIdInvalid
)
from dotenv import load_dotenv
import yt_dlp

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

# ========================= Config =========================
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
SESSION_STRING = os.getenv("SESSION_STRING")
PORT = int(os.getenv("PORT", 8080))
ASSISTANT_USERNAME = os.getenv("ASSISTANT_USERNAME")

TMP_MEDIA_DIR = os.getenv("TMP_MEDIA_DIR", "/tmp/tgmedia")
os.makedirs(TMP_MEDIA_DIR, exist_ok=True)

if not API_ID or not API_HASH or not BOT_TOKEN:
    raise RuntimeError("ENV missing: API_ID, API_HASH, BOT_TOKEN are required")

bot = Client("bot", api_id=int(API_ID), api_hash=API_HASH, bot_token=BOT_TOKEN)

userbot_available = False
userbot = None
if SESSION_STRING:
    try:
        userbot = Client("userbot", api_id=int(API_ID), api_hash=API_HASH, session_string=SESSION_STRING)
        userbot_available = True
        logger.info("✅ UserBot configured")
    except Exception as e:
        logger.error(f"UserBot error: {e}")
else:
    logger.warning("⚠️ No SESSION_STRING provided. Music playback will not be available.")

# ========================= PyTgCalls =========================
pytgcalls_available = False
calls = None
HAVE_MEDIA_STREAM = False

if userbot_available:
    try:
        from pytgcalls import PyTgCalls
        calls = PyTgCalls(userbot)
        asyncio.get_event_loop().run_until_complete(calls.start())  # ✅ تشغيل المكالمات
        try:
            from pytgcalls.types import MediaStream, AudioQuality
            HAVE_MEDIA_STREAM = True
        except Exception:
            HAVE_MEDIA_STREAM = False
        pytgcalls_available = True
        logger.info("✅ pytgcalls imported and started successfully")
    except Exception as e:
        logger.error(f"❌ pytgcalls error: {e}")

# ========================= State =========================
stats = {
    'messages': 0, 'commands': 0, 'users': set(), 'groups': set(),
    'songs_searched': 0, 'songs_played': 0, 'start_time': time.time()
}
music_queue: Dict[int, List[Dict]] = {}
currently_playing: Dict[int, Dict] = {}

# ========================= YouTube =========================
ydl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'geo_bypass': True,
    'ignoreerrors': True,
    'retries': 5,
}

async def download_song(query: str):
    try:
        logger.info(f"🔍 Searching: {query}")
        stats['songs_searched'] += 1
        def extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if query.startswith(('http://', 'https://')):
                    info = ydl.extract_info(query, download=False)
                else:
                    info = ydl.extract_info(f"ytsearch:{query}", download=False)
                    if 'entries' in info and info['entries']:
                        info = info['entries'][0]
                return info
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, extract)
        if not info:
            return None
        return {
            'id': info.get('id', ''),
            'title': info.get('title', 'Unknown'),
            'url': info.get('url'),
            'duration': info.get('duration', 0),
            'thumbnail': info.get('thumbnail', ''),
            'webpage_url': info.get('webpage_url', ''),
            'uploader': info.get('uploader', 'Unknown'),
        }
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None

def format_duration(seconds):
    if not seconds:
        return "مباشر"
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d}" if hours else f"{mins:02d}:{secs:02d}"

# ========================= Playback =========================
async def play_next_song(chat_id: int):
    if not pytgcalls_available or not calls:
        return False
    if chat_id not in music_queue or not music_queue[chat_id]:
        try:
            await calls.leave_call(chat_id)
            if chat_id in currently_playing:
                del currently_playing[chat_id]
            await bot.send_message(chat_id, "📭 انتهت القائمة")
        except Exception:
            pass
        return False
    next_song = music_queue[chat_id].pop(0)
    try:
        await calls.play(chat_id, next_song['url'])
        currently_playing[chat_id] = next_song
        stats['songs_played'] += 1
        await bot.send_message(
            chat_id,
            f"▶️ **يتم التشغيل:**\n🎵 {next_song['title']}\n⏱️ {format_duration(next_song['duration'])}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏸️", "pause"),
                                                InlineKeyboardButton("⏭️", "skip"),
                                                InlineKeyboardButton("⏹️", "stop")]])
        )
        return True
    except Exception as e:
        logger.error(f"❌ Play error: {e}")
        return False

# ========================= Commands =========================
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message: Message):
    await message.reply_text("🎵 مرحباً! أنا بوت تشغيل موسيقى.\nاستخدم /play لتشغيل الأغاني.")

@bot.on_message(filters.command(["play", "p"]) & (filters.group | filters.channel))
async def play_cmd(client, message: Message):
    chat_id = message.chat.id
    if not userbot_available or not pytgcalls_available:
        return await message.reply_text("❌ التشغيل غير متاح حالياً.")
    if len(message.command) < 2:
        if chat_id in music_queue and music_queue[chat_id]:
            await play_next_song(chat_id)
            return
        if message.reply_to_message:
            link = re.search(r'(https?://\S+)', message.reply_to_message.text or "")
            if link:
                info = await download_song(link.group(1))
                if not info:
                    return await message.reply_text("❌ لم أستطع استخراج معلومات الأغنية.")
                music_queue.setdefault(chat_id, []).append(info)
                await play_next_song(chat_id)
                return
        return await message.reply_text("❌ لا يوجد شيء للتشغيل.")
    query = " ".join(message.command[1:])
    info = await download_song(query)
    if not info:
        return await message.reply_text("❌ لم أستطع العثور على الأغنية.")
    music_queue.setdefault(chat_id, []).append(info)
    if chat_id not in currently_playing:
        await play_next_song(chat_id)
    await message.reply_text(f"✅ تمت إضافة: {info['title']}")

# ========================= Run =========================
async def main():
    await bot.start()
    if userbot:
        await userbot.start()
    logger.info("✅ Bot started")
    await idle()

from pyrogram import idle
if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
