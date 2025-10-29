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
    UserAlreadyParticipant, ChatAdminRequired, UserNotParticipant, PeerIdInvalid, RPCError
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

# ========================= Compatibility Patch (Fixes GroupcallForbidden Error) =========================
try:
    # Check if GroupcallForbidden exists, if not, create it for compatibility
    from pyrogram.errors import GroupcallForbidden
except ImportError:
    class GroupcallForbidden(RPCError):
        def __init__(self, *args, **kwargs):
            super().__init__("GroupcallForbidden")
    # Add the newly created class to the pyrogram.errors module
    import pyrogram.errors
    pyrogram.errors.GroupcallForbidden = GroupcallForbidden
    logger.info("🩹 Applied compatibility patch for GroupcallForbidden.")


# ========================= PyTgCalls setup =========================
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
                if 'youtube.com/playlist?list=' in query:
                     # For now, we only take the first video of a playlist to avoid complexity
                    info = ydl.extract_info(query, download=False, process=False)['entries'][0]
                    info = ydl.extract_info(info['url'], download=False) # Re-extract with full info
                elif query.startswith(('http://', 'https://')):
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
def generate_image_style_keyboard(is_paused: bool) -> InlineKeyboardMarkup:
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

# PyTgCalls Safe Wrappers
async def safe_play(chat_id: int, url: str):
    if HAVE_MEDIA_STREAM:
        from pytgcalls.types import AudioQuality, MediaStream
        return await calls.play(chat_id, MediaStream(url, audio_parameters=AudioQuality.HIGH))
    return await calls.play(chat_id, url)

async def safe_leave(chat_id: int):
    return await calls.leave_group_call(chat_id)
async def safe_pause(chat_id: int):
    return await calls.pause_stream(chat_id)
async def safe_resume(chat_id: int):
    return await calls.resume_stream(chat_id)

currently_playing: Dict[int, Dict] = {}
music_queue: Dict[int, List[Dict]] = {}
active_messages: Dict[int, int] = {} # To store the ID of the "now playing" message

async def play_next_song(chat_id: int, requested_by: str = "Unknown"):
    # Clean up old message first
    if old_msg_id := active_messages.pop(chat_id, None):
        try:
            await bot.delete_messages(chat_id, old_msg_id)
        except Exception:
            pass

    if chat_id not in music_queue or not music_queue[chat_id]:
        await safe_leave(chat_id)
        if chat_id in currently_playing: del currently_playing[chat_id]
        try:
            await bot.send_message(chat_id, "📭 انتهت قائمة الانتظار.")
        except: pass
        return

    next_song = music_queue[chat_id].pop(0)
    currently_playing[chat_id] = next_song
    
    try:
        await safe_play(chat_id, next_song['url'])
        dur = int(next_song.get('duration', 0))
        
        keyboard = generate_image_style_keyboard(is_paused=False)
        message_text = (
            f"**YT sτяєαмiиg ♪**\n\n"
            f"▸ **ᴛɪᴛʟᴇ :** {next_song.get('title', 'Unknown Title')}\n"
            f"▸ **ᴅᴜʀᴀᴛɪᴏɴ :** {format_duration(dur)}\n"
            f"▸ **ʀᴇǫᴜᴇsᴛᴇᴅ ʙʏ :** {requested_by}"
        )
        sent_message = await bot.send_photo(
            chat_id,
            # Placeholder image URL (tennis racket)
            photo="https://telegra.ph/file/b9289a878562d2a23354c.jpg",
            caption=message_text,
            reply_markup=keyboard
        )
        active_messages[chat_id] = sent_message.id
    except Exception as e:
        logger.error(f"Play error: {e}")
        await bot.send_message(chat_id, f"❌ حدث خطأ أثناء محاولة التشغيل:\n`{e}`")


# ========================= Commands =========================

# ✨✨✨ ✨✨✨ ✨✨✨
# ## أمر /start و /help (تمت إضافته) ##
# ✨✨✨ ✨✨✨ ✨✨✨
@bot.on_message(filters.command(["start", "help"]) & (filters.group | filters.private))
async def start_cmd(client, message: Message):
    if message.chat.type == "private":
        text = (
            "👋 **أهلاً بك! أنا بوت تشغيل الموسيقى للمحادثات الصوتية.**\n\n"
            "للبدء:\n"
            "1. **أضفني إلى مجموعتك.**\n"
            "2. **اجعلني مشرفًا** (مع صلاحية **إدارة المحادثات الصوتية**).\n"
            "3. **ابدأ محادثة صوتية** في المجموعة.\n"
            "4. استخدم الأمر `/play <اسم الأغنية>` للتشغيل.\n\n"
            "**ملاحظة:** يجب أن يكون الحساب المساعد (Userbot) الذي استخدمته لإنشاء `SESSION_STRING` مضافاً إلى المجموعة أيضاً."
        )
    else:
        text = (
            "**استخدامات البوت:**\n"
            "▸ `/play <اسم/رابط>`: لتشغيل أغنية أو فيديو من يوتيوب.\n"
            "▸ `/skip`: لتخطي الأغنية الحالية.\n"
            "▸ `/stop`: لإيقاف التشغيل ومغادرة المكالمة.\n"
            "▸ `/pause` / `/resume`: لإيقاف/استئناف التشغيل.\n"
            "**تذكر أن تمنحني صلاحية إدارة المحادثات الصوتية!**"
        )
        
    await message.reply_text(text)
# ✨✨✨ ✨✨✨ ✨✨✨


@bot.on_message(filters.command(["play", "p"]) & filters.group)
async def play_cmd(client, message: Message):
    if not userbot_available or not pytgcalls_available:
        return await message.reply_text("❌ خدمة التشغيل غير مفعلة. تأكد من صحة `SESSION_STRING`.")
    
    query = " ".join(message.command[1:])
    if not query and message.reply_to_message:
        query = message.reply_to_message.text or message.reply_to_message.caption
    
    if not query:
        return await message.reply_text("❓ يرجى تحديد اسم الأغنية أو رابطها. مثال: `/play Closer`")

    msg = await message.reply_text("🔄 **جاري البحث...**")
    song_info = await download_song(query)
    
    if not song_info:
        return await msg.edit("❌ لم أجد الأغنية أو الرابط غير صالح.")
        
    chat_id = message.chat.id
    if chat_id not in music_queue:
        music_queue[chat_id] = []
        
    music_queue[chat_id].append(song_info)
    
    if chat_id not in currently_playing:
        await msg.delete()
        try:
            await calls.join_group_call(chat_id)
        except Exception as e:
            if "already joined" not in str(e).lower():
                 logger.warning(f"Join call failed: {e}")
        await play_next_song(chat_id, message.from_user.mention)
    else:
        await msg.edit(f"✅ **تمت الإضافة للقائمة:**\n`{song_info['title']}`")

# ========================= Callback Query Handler =========================
@bot.on_callback_query(filters.regex("^(pause|resume|skip|stop|previous|close_menu)$"))
async def playback_controls_cq(client, query: CallbackQuery):
    chat_id = query.message.chat.id
    data = query.data

    if data == "close_menu":
        await query.message.delete()
        active_messages.pop(chat_id, None)
        return await query.answer("Menu closed.")

    currently_playing_song = currently_playing.get(chat_id)
    if not currently_playing_song:
        await query.message.delete()
        return await query.answer("❌ التشغيل متوقف بالفعل.", show_alert=True)
        
    if data == "pause":
        await safe_pause(chat_id)
        keyboard = generate_image_style_keyboard(is_paused=True)
        await query.message.edit_reply_markup(keyboard)
        await query.answer("⏸️ تم الإيقاف المؤقت")
    
    elif data == "resume":
        await safe_resume(chat_id)
        keyboard = generate_image_style_keyboard(is_paused=False)
        await query.message.edit_reply_markup(keyboard)
        await query.answer("▶️ تم الاستئناف")

    elif data == "skip":
        await query.answer("⏭️ جاري التخطي...")
        await play_next_song(chat_id)

    elif data == "stop":
        await query.answer("⏹️ جاري الإيقاف...")
        music_queue[chat_id] = []
        await safe_leave(chat_id)
        if chat_id in currently_playing: del currently_playing[chat_id]
        # Edit the message caption only if it still exists
        try:
            await query.message.edit_caption("⏹️ تم إيقاف التشغيل.")
        except Exception:
            pass
        active_messages.pop(chat_id, None)
        
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
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()
    logger.info(f"🌍 Web server started on port {os.environ.get('PORT', 8080)}")


# ========================= Main Runner =========================
async def main():
    logger.info("Starting clients...")
    await bot.start()
    bot_info = await bot.get_me()
    logger.info(f"✅ Bot started as @{bot_info.username}")
    
    if userbot_available and userbot:
        await userbot.start()
        user_info = await userbot.get_me()
        logger.info(f"✅ UserBot started as {user_info.first_name}")

    if pytgcalls_available and calls:
        await calls.start()
        logger.info("✅ Pytgcalls successfully started")
        
    await ensure_ffmpeg()
    
    web_task = asyncio.create_task(run_web_server())
    
    logger.info("🤖 Bot is now online and ready!")
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Bot shutting down...")
