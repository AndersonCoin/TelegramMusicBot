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
import stat
from typing import Dict, List

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import (
    UserAlreadyParticipant, ChatAdminRequired, UserNotParticipant, PeerIdInvalid
)
from dotenv import load_dotenv
from aiohttp import web
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

# متغيرات زر القناة (من ملف .env)
CHANNEL_NAME = os.getenv("CHANNEL_NAME", "Channel")
CHANNEL_URL = os.getenv("CHANNEL_URL")

# مسار تخزين الوسائط المؤقتة
TMP_MEDIA_DIR = os.getenv("TMP_MEDIA_DIR", "/tmp/tgmedia")
os.makedirs(TMP_MEDIA_DIR, exist_ok=True)

# ========================= Clients =========================
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
        userbot = None
else:
    logger.warning("⚠️ No SESSION_STRING provided. Music playback will not be available.")
    userbot = None

# ========================= PyTgCalls setup (هذا هو الجزء المفقود الذي سبب الخطأ) =========================
pytgcalls_available = False
calls = None
HAVE_MEDIA_STREAM = False

if userbot_available:
    try:
        from pytgcalls import PyTgCalls
        calls = PyTgCalls(userbot)
        try:
            from pytgcalls.types import MediaStream, AudioQuality
            HAVE_MEDIA_STREAM = True
        except Exception:
            HAVE_MEDIA_STREAM = False
        pytgcalls_available = True
        logger.info("✅ pytgcalls imported successfully")
    except Exception as e:
        logger.error(f"❌ pytgcalls error: {e}")

# ========================= FFmpeg Ensurer =========================
async def ensure_ffmpeg():
    # (هنا الكود الخاص بـ ffmpeg، لا حاجة لتغييره)
    if shutil.which("ffmpeg"):
        logger.info("✅ ffmpeg is already available.")
        return
    logger.warning("ffmpeg not found. Please install it on your system.")


# ========================= YouTube & Download Helpers =========================
ydl_opts = {
    'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True,
    'no_warnings': True, 'extract_flat': False, 'geo_bypass': True,
    'ignoreerrors': True, 'retries': 5, 'fragment_retries': 5
}

async def download_song(query: str):
    try:
        logger.info(f"🔍 Searching: {query}")
        def extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if query.startswith(('http://', 'https://')):
                    info = ydl.extract_info(query, download=False)
                else:
                    info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
                return info
        info = await asyncio.get_event_loop().run_in_executor(None, extract)
        return {
            'id': info.get('id', ''), 'title': info.get('title', 'Unknown'),
            'url': info.get('url'), 'duration': info.get('duration', 0),
            'webpage_url': info.get('webpage_url', ''),
        }
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None

def format_duration(seconds):
    if not seconds: return "مباشر"
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d}" if hours else f"{mins:02d}:{secs:02d}"


# ========================= Core Playback & UI =========================
# (هنا باقي الدوال المساعدة مثل resolve_target_chat_id, join_chat, etc.)
# ...

# دالة إنشاء الأزرار الجديدة بأسلوب الصورة
def generate_image_style_keyboard(is_paused: bool, song_info: dict) -> InlineKeyboardMarkup:
    play_pause_icon = "▶️" if is_paused else "⏸️"
    play_pause_callback = "resume" if is_paused else "pause"

    keyboard = [
        [
            InlineKeyboardButton("⏮", callback_data="previous"),
            InlineKeyboardButton(play_pause_icon, callback_data=play_pause_callback),
            InlineKeyboardButton("⏭️", callback_data="skip"),
            InlineKeyboardButton("⏹️", callback_data="stop"),
        ],
    ]
    if CHANNEL_URL and CHANNEL_NAME:
        keyboard.append([InlineKeyboardButton(f"⟫ {CHANNEL_NAME} ⟪", url=CHANNEL_URL)])
    keyboard.append([InlineKeyboardButton("乂", callback_data="close_menu")])
    return InlineKeyboardMarkup(keyboard)

# باقي الدوال المساعدة (مثل safe_play, safe_leave)
async def safe_play(chat_id: int, url: str):
    return await calls.play(chat_id, url)
async def safe_leave(chat_id: int):
    return await calls.leave_group_call(chat_id)
async def safe_pause(chat_id: int):
    return await calls.pause_stream(chat_id)
async def safe_resume(chat_id: int):
    return await calls.resume_stream(chat_id)

currently_playing: Dict[int, Dict] = {}
music_queue: Dict[int, List[Dict]] = {}
playback_timers: Dict[int, asyncio.Task] = {}

def cancel_timer(chat_id: int):
    t = playback_timers.pop(chat_id, None)
    if t and not t.done(): t.cancel()

async def play_next_song(chat_id: int, requested_by: str = "Unknown"):
    if chat_id not in music_queue or not music_queue[chat_id]:
        await safe_leave(chat_id)
        if chat_id in currently_playing: del currently_playing[chat_id]
        await bot.send_message(chat_id, "📭 انتهت قائمة الانتظار.")
        return

    next_song = music_queue[chat_id].pop(0)
    currently_playing[chat_id] = next_song
    
    try:
        await safe_play(chat_id, next_song['url'])
        dur = int(next_song.get('duration', 0))
        
        keyboard = generate_image_style_keyboard(is_paused=False, song_info=next_song)
        message_text = (
            f"**YT sτяєαмiиg ♪**\n\n"
            f"▸ **ᴛɪᴛʟᴇ :** {next_song.get('title', 'Unknown Title')}\n"
            f"▸ **ᴅᴜʀᴀᴛɪᴏɴ :** {format_duration(dur)}\n"
            f"▸ **ʀᴇǫᴜᴇsᴛᴇᴅ ʙʏ :** {requested_by}"
        )
        await bot.send_photo(
            chat_id,
            photo="https://telegra.ph/file/b9289a878562d2a23354c.jpg",
            caption=message_text,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Play error: {e}")

# ========================= Commands =========================
@bot.on_message(filters.command(["play", "p"]) & filters.group)
async def play_cmd(client, message: Message):
    if not userbot_available or not pytgcalls_available:
        return await message.reply_text("❌ خدمة التشغيل غير مفعلة.")
    
    query = " ".join(message.command[1:])
    if not query:
        return await message.reply_text("❓ يرجى تحديد اسم الأغنية. مثال: `/play Closer`")

    msg = await message.reply_text("🔄 **جاري البحث...**")
    song_info = await download_song(query)
    
    if not song_info:
        return await msg.edit("❌ لم أجد الأغنية.")
        
    chat_id = message.chat.id
    if chat_id not in music_queue:
        music_queue[chat_id] = []
        
    music_queue[chat_id].append(song_info)
    
    if chat_id not in currently_playing:
        await msg.delete()
        # Join call logic (simplified)
        try:
            await calls.join_group_call(chat_id)
        except Exception as e:
            logger.warning(f"Join call failed: {e}")
        await play_next_song(chat_id, message.from_user.mention)
    else:
        await msg.edit(f"✅ **تمت الإضافة للقائمة:** {song_info['title']}")

# ========================= Callback Query Handler =========================
@bot.on_callback_query(filters.regex("^(pause|resume|skip|stop|previous|close_menu)$"))
async def playback_controls_cq(client, query: CallbackQuery):
    chat_id = query.message.chat.id
    data = query.data

    if data == "close_menu":
        await query.message.delete()
        return await query.answer("Menu closed.")

    currently_playing_song = currently_playing.get(chat_id)
    if not currently_playing_song:
        await query.message.delete()
        return await query.answer("❌ التشغيل متوقف بالفعل.", show_alert=True)
        
    if data == "pause":
        await safe_pause(chat_id)
        keyboard = generate_image_style_keyboard(is_paused=True, song_info=currently_playing_song)
        await query.message.edit_reply_markup(keyboard)
        await query.answer("⏸️ تم الإيقاف المؤقت")
    
    elif data == "resume":
        await safe_resume(chat_id)
        keyboard = generate_image_style_keyboard(is_paused=False, song_info=currently_playing_song)
        await query.message.edit_reply_markup(keyboard)
        await query.answer("▶️ تم الاستئناف")

    elif data == "skip":
        await query.answer("⏭️ جاري التخطي...")
        await query.message.delete()
        await play_next_song(chat_id) # requester info is lost on skip, can be improved

    elif data == "stop":
        await query.answer("⏹️ جاري الإيقاف...")
        music_queue[chat_id] = []
        await safe_leave(chat_id)
        if chat_id in currently_playing: del currently_playing[chat_id]
        await query.message.edit_caption("⏹️ تم إيقاف التشغيل.")
        
    elif data == "previous":
        await query.answer("⏮️ هذه الميزة قيد التطوير!", show_alert=True)


# ========================= Web Server (for uptime) =========================
async def handle_root(request):
    return web.Response(text="Bot is running!")

async def run_web_server():
    app = web.Application()
    app.router.add_get('/', handle_root)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"🌍 Web server started on port {PORT}")


# ========================= Main Runner =========================
async def main():
    global bot_username
    logger.info("Starting clients...")
    await bot.start()
    bot_info = await bot.get_me()
    bot_username = bot_info.username
    logger.info(f"✅ Bot started as @{bot_username}")
    
    if userbot_available and userbot:
        await userbot.start()
        user_info = await userbot.get_me()
        logger.info(f"✅ UserBot started as {user_info.first_name}")

    if pytgcalls_available and calls:
        await calls.start()
        logger.info("✅ Pytgcalls started")
        
    await ensure_ffmpeg()
    
    web_task = asyncio.create_task(run_web_server())
    
    logger.info("🤖 Bot is now online and ready!")
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Bot shutting down...")
