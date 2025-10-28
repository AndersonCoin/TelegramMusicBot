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
from typing import Dict, List, Union

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
ASSISTANT_USERNAME = os.getenv("ASSISTANT_USERNAME", "my_assistant")
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/RosaliaChannel") # Added for the button

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

# <<< START OF ADDED CODE: COMPATIBILITY PATCH >>>
# ========================= Compat Patch (fix GroupcallForbidden import) =========================
try:
    import pyrogram.errors as _p_err
    if not hasattr(_p_err, "GroupcallForbidden"):
        class GroupcallForbidden(_p_err.RPCError if hasattr(_p_err, "RPCError") else Exception):
            ID = "GROUPCALL_FORBIDDEN"
            def __init__(self, *args, **kwargs):
                super().__init__("The user is not allowed to join the group call")
        _p_err.GroupcallForbidden = GroupcallForbidden
        logger.info("🩹 Applied compat patch: pyrogram.errors.GroupcallForbidden")
except Exception as _e:
    logger.warning(f"Compat patch failed: {_e}")
# <<< END OF ADDED CODE >>>

# ========================= PyTgCalls Setup =========================
pytgcalls_available = False
calls = None
if userbot_available:
    try:
        from pytgcalls import PyTgCalls
        from pytgcalls.types import AudioQuality, MediaStream
        calls = PyTgCalls(userbot)
        pytgcalls_available = True
        logger.info("✅ pytgcalls imported successfully")
    except Exception as e:
        logger.error(f"❌ pytgcalls error: {e}")

# ========================= State & Helpers =========================
# ... (The state and helper functions remain the same as the previous correct version) ...
stats = { 'songs_played': 0, 'start_time': time.time() }
music_queue: Dict[int, List[Dict]] = {}
currently_playing: Dict[int, Dict] = {}
bot_username = None
playback_timers: Dict[int, asyncio.Task] = {}

def format_duration(seconds):
    if not seconds: return "مباشر"
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d}" if hours else f"{mins:02d}:{secs:02d}"

async def download_song(query: str):
    ydl_opts = {
        'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True, 'no_warnings': True,
        'default_search': 'ytsearch', 'geo_bypass': True,
        'extractor_args': {'youtube': {'player_client': ['android']}}
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if 'entries' in info: info = info['entries'][0]
        return {
            'id': info.get('id', ''), 'title': info.get('title', 'Unknown Title'),
            'url': info.get('url'), 'duration': info.get('duration', 0),
            'thumbnail': info.get('thumbnail', ''), 'webpage_url': info.get('webpage_url', ''),
            'uploader': info.get('uploader', 'Unknown Artist'),
        }
    except Exception as e:
        logger.error(f"yt-dlp error: {e}")
        return None

async def resolve_target_chat_id(chat): return getattr(chat, 'linked_chat', chat).id

async def join_chat(chat_id: int, invoker: Message = None) -> bool:
    if not userbot_available: return False
    try:
        chat_obj = await bot.get_chat(chat_id)
        if chat_obj.username: await userbot.join_chat(chat_obj.username)
        else:
            invite_link = await bot.export_chat_invite_link(chat_id)
            await userbot.join_chat(invite_link)
        return True
    except UserAlreadyParticipant: return True
    except Exception as e:
        if invoker: await invoker.reply(f"❌ فشل انضمام المساعد. تأكد أنني مشرف. الخطأ: {e}")
        return False

def cancel_timer(chat_id: int):
    t = playback_timers.pop(chat_id, None)
    if t and not t.done(): t.cancel()

def set_timer(chat_id: int, task: asyncio.Task):
    cancel_timer(chat_id)
    playback_timers[chat_id] = task

def create_playback_timer(chat_id: int, song_id: str, sleep_sec: float) -> asyncio.Task:
    async def runner():
        await asyncio.sleep(max(3, sleep_sec))
        cur = currently_playing.get(chat_id)
        if cur and cur.get('id') == song_id: await play_next_song(chat_id, from_auto=True)
    return asyncio.create_task(runner())

async def safe_play(chat_id, url): await calls.play(chat_id, MediaStream(url, audio_parameters=AudioQuality.HIGH))
async def safe_change_stream(chat_id, url): await calls.change_stream(chat_id, MediaStream(url, audio_parameters=AudioQuality.HIGH))
async def safe_leave(chat_id): await calls.leave_group_call(chat_id)
async def safe_pause(chat_id): await calls.pause_stream(chat_id)
async def safe_resume(chat_id): await calls.resume_stream(chat_id)

# ========================= Music Controls & Callbacks =========================
def music_controls_keyboard(chat_id: int, is_paused: bool = False, song_url: str = ""):
    play_pause_button = InlineKeyboardButton("▶️ استئناف" if is_paused else "⏸️ إيقاف مؤقت", callback_data=f"{'resume' if is_paused else 'pause'}_{chat_id}")
    row1 = [play_pause_button, InlineKeyboardButton("⏭️ تخطي", callback_data=f"skip_{chat_id}"), InlineKeyboardButton("⏹️ إيقاف", callback_data=f"stop_{chat_id}")]
    row2 = []
    if song_url: row2.append(InlineKeyboardButton("🔗 الرابط", url=song_url))
    row2.append(InlineKeyboardButton("🔔 القناة", url=CHANNEL_URL))
    return InlineKeyboardMarkup([row1, row2])

@bot.on_callback_query(filters.regex(r"^(pause|resume|skip|stop)_"))
async def controls_callback_handler(_, query: CallbackQuery):
    try:
        command, chat_id_str = query.data.split("_", 1)
        chat_id = int(chat_id_str)
    except ValueError: return await query.answer("خطأ.", show_alert=True)
    
    cur = currently_playing.get(chat_id)
    
    if command == "pause":
        if not cur or cur.get('_paused_at'): return await query.answer("متوقف بالفعل.", show_alert=False)
        try:
            await safe_pause(chat_id)
            cancel_timer(chat_id)
            cur['_paused_at'] = time.time()
            await query.answer("تم الإيقاف المؤقت.")
            await query.edit_message_reply_markup(reply_markup=music_controls_keyboard(chat_id, is_paused=True, song_url=cur.get('webpage_url')))
        except Exception as e: await query.answer(f"❌ فشل: {e}", show_alert=True)

    elif command == "resume":
        if not cur or not cur.get('_paused_at'): return await query.answer("يعمل بالفعل.", show_alert=False)
        try:
            await safe_resume(chat_id)
            paused_duration = time.time() - cur['_paused_at']
            cur['_started_at'] += paused_duration
            cur['_paused_at'] = None
            elapsed = time.time() - cur['_started_at']
            remaining = max(3, cur['duration'] - elapsed)
            set_timer(chat_id, create_playback_timer(chat_id, cur.get('id', ''), remaining + 1))
            await query.answer("تم الاستئناف.")
            await query.edit_message_reply_markup(reply_markup=music_controls_keyboard(chat_id, is_paused=False, song_url=cur.get('webpage_url')))
        except Exception as e: await query.answer(f"❌ فشل: {e}", show_alert=True)

    elif command == "skip":
        await query.answer("جارٍ التخطي...")
        await query.message.delete()
        await play_next_song(chat_id, from_skip=True, user_mention=query.from_user.mention)

    elif command == "stop":
        await query.answer("جارٍ الإيقاف...")
        cancel_timer(chat_id)
        await safe_leave(chat_id)
        title = cur['title'] if cur else "..."
        if chat_id in currently_playing: del currently_playing[chat_id]
        if chat_id in music_queue: music_queue[chat_id] = []
        try:
            await query.edit_message_caption(caption=f"⏹️ **تم إيقاف التشغيل بواسطة {query.from_user.mention}**\n🎵 `{title}`", reply_markup=None)
        except:
            await query.edit_message_text(f"⏹️ **تم إيقاف التشغيل بواسطة {query.from_user.mention}**\n🎵 `{title}`", reply_markup=None, disable_web_page_preview=True)

# ========================= Core Playback & Commands =========================
async def play_next_song(chat_id, from_skip=False, from_auto=False, user_mention="تلقائي"):
    if not music_queue.get(chat_id):
        await safe_leave(chat_id)
        if chat_id in currently_playing: del currently_playing[chat_id]
        if not from_auto: await bot.send_message(chat_id, "📭 انتهت القائمة.")
        return
    
    next_song = music_queue[chat_id].pop(0)
    try:
        stream_method = safe_change_stream if currently_playing.get(chat_id) else safe_play
        await stream_method(chat_id, next_song['url'])
        
        next_song.update({'_started_at': time.time(), '_paused_at': None})
        currently_playing[chat_id] = next_song
        stats['songs_played'] += 1
        
        dur = int(next_song.get('duration', 0))
        if dur > 0: set_timer(chat_id, create_playback_timer(chat_id, next_song.get('id', ''), dur + 2))

        keyboard = music_controls_keyboard(chat_id, is_paused=False, song_url=next_song.get('webpage_url'))
        caption = f"⏭️ **تم التخطي بواسطة {user_mention}**\n\n" if from_skip else ""
        caption += f"▶️ **يتم التشغيل الآن**\n🎵 **العنوان:** `{next_song['title']}`\n⏱️ **المدة:** {format_duration(dur)}\n👤 **القناة:** {next_song['uploader']}"
        
        if next_song.get('thumbnail'):
            await bot.send_photo(chat_id, photo=next_song['thumbnail'], caption=caption, reply_markup=keyboard)
        else:
            await bot.send_message(chat_id, caption, reply_markup=keyboard, disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"❌ Play error in {chat_id}: {e}")
        await bot.send_message(chat_id, f"❌ خطأ في التشغيل: {e}")
        await play_next_song(chat_id)

@bot.on_message(filters.command(["play", "p"]) & (filters.group | filters.channel))
async def play_cmd(_, message: Message):
    chat_id = await resolve_target_chat_id(message.chat)
    if not pytgcalls_available: return await message.reply("❌ **التشغيل غير متاح حالياً.**")
    
    query = " ".join(message.command[1:])
    if not query: return await message.reply("🤔 ماذا تريد أن أُشغل؟")

    msg = await message.reply_text("🔄 **جاري التحضير...**")
    if not currently_playing.get(chat_id) and not await join_chat(chat_id, invoker=message):
        return await msg.edit("❌ فشل انضمام المساعد.")

    await msg.edit("🔍 **جاري البحث...**")
    song_info = await download_song(query)
    if not song_info: return await msg.edit("❌ لم أجد الأغنية!")

    if chat_id not in music_queue: music_queue[chat_id] = []
    music_queue[chat_id].append(song_info)
    
    if not currently_playing.get(chat_id):
        await msg.delete()
        await play_next_song(chat_id)
    else:
        await msg.edit(f"✅ **تمت الإضافة للقائمة #{len(music_queue[chat_id])}**\n🎵 `{song_info['title']}`")

# ... (Other simple commands like /start, /skip, etc.) ...
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(_, m): await m.reply("أهلاً بك! أضفني إلى مجموعة وابدأ التشغيل.")

# ========================= Web Server & Main Execution =========================
async def health_check(request):
    return web.Response(text="OK", content_type="text/plain")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    try:
        await site.start()
        logger.info(f"✅ Web server started on port {PORT}")
    except Exception as e:
        logger.error(f"❌ Failed to start web server: {e}")

async def main():
    global bot_username
    logger.info("Initializing...")
    
    # <<< START OF MODIFIED SECTION: REORDERED STARTUP >>>
    # 1. Start the web server immediately to satisfy the hosting platform
    await start_web_server()

    # 2. Now, start the Telegram clients
    await bot.start()
    me = await bot.get_me()
    bot_username = me.username
    logger.info(f"✅ Bot @{bot_username} started.")

    if userbot_available:
        await userbot.start()
        me_user = await userbot.get_me()
        logger.info(f"✅ UserBot {me_user.first_name} started.")
        if pytgcalls_available:
            await calls.start()
            logger.info("✅ PyTgCalls started.")
    
    logger.info("🚀 Bot is fully operational!")
    await asyncio.Event().wait()
    # <<< END OF MODIFIED SECTION >>>

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot shutting down...")
