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
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import (
    UserAlreadyParticipant, ChatAdminRequired, UserNotParticipant, PeerIdInvalid
)
from dotenv import load_dotenv
from aiohttp import web
import yt_dlp

load_dotenv()

# --- Logging and Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
SESSION_STRING = os.getenv("SESSION_STRING")
PORT = int(os.getenv("PORT", 8080))
ASSISTANT_USERNAME = os.getenv("ASSISTANT_USERNAME")
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/RosaliaChannel") # For the button

# --- Client Initialization ---
if not all([API_ID, API_HASH, BOT_TOKEN]):
    raise RuntimeError("Missing required environment variables: API_ID, API_HASH, BOT_TOKEN")

bot = Client("bot", api_id=int(API_ID), api_hash=API_HASH, bot_token=BOT_TOKEN)

userbot = None
userbot_available = bool(SESSION_STRING)
if userbot_available:
    try:
        userbot = Client("userbot", api_id=int(API_ID), api_hash=API_HASH, session_string=SESSION_STRING)
        logger.info("✅ UserBot configured.")
    except Exception as e:
        logger.error(f"UserBot init error: {e}")
        userbot = None
        userbot_available = False
else:
    logger.warning("⚠️ No SESSION_STRING provided. Music playback will be disabled.")

# --- Compatibility Patch ---
try:
    import pyrogram.errors as _p_err
    if not hasattr(_p_err, "GroupcallForbidden"):
        class GroupcallForbidden(_p_err.RPCError if hasattr(_p_err, "RPCError") else Exception):
            ID = "GROUPCALL_FORBIDDEN"
        _p_err.GroupcallForbidden = GroupcallForbidden
        logger.info("🩹 Applied compat patch for GroupcallForbidden.")
except Exception as _e:
    logger.warning(f"Compat patch failed: {_e}")

# --- PyTgCalls Setup ---
pytgcalls_available = False
calls = None
if userbot_available:
    try:
        from pytgcalls import PyTgCalls
        from pytgcalls.types import AudioQuality, MediaStream
        calls = PyTgCalls(userbot)
        pytgcalls_available = True
        logger.info("✅ pytgcalls initialized.")
    except Exception as e:
        logger.error(f"❌ pytgcalls init error: {e}")

# --- State Management ---
music_queue: Dict[int, List[Dict]] = {}
currently_playing: Dict[int, Dict] = {}
bot_username = None
playback_timers: Dict[int, asyncio.Task] = {}

# --- Helper Functions ---
def format_duration(seconds):
    if not seconds: return "مباشر"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

async def download_song(query: str):
    ydl_opts = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True, 'default_search': 'ytsearch'}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if 'entries' in info: info = info['entries'][0]
        return {
            'id': info.get('id', ''), 'title': info.get('title', 'Unknown'), 'url': info.get('url'),
            'duration': info.get('duration', 0), 'thumbnail': info.get('thumbnail'),
            'webpage_url': info.get('webpage_url'), 'uploader': info.get('uploader', 'Unknown'),
        }
    except Exception as e:
        logger.error(f"yt-dlp error: {e}")
        return None

async def resolve_target_chat_id(chat): return getattr(chat, 'linked_chat', chat).id

async def join_chat(chat_id, invoker):
    if not userbot_available: return False
    try:
        chat_obj = await bot.get_chat(chat_id)
        if chat_obj.username: await userbot.join_chat(chat_obj.username)
        else:
            link = await bot.export_chat_invite_link(chat_id)
            await userbot.join_chat(link)
        return True
    except UserAlreadyParticipant: return True
    except Exception as e:
        if invoker: await invoker.reply(f"❌ فشل انضمام المساعد: {e}")
        return False

def cancel_timer(chat_id):
    if (t := playback_timers.pop(chat_id, None)) and not t.done(): t.cancel()

def set_timer(chat_id, task):
    cancel_timer(chat_id)
    playback_timers[chat_id] = task

def create_playback_timer(chat_id, song_id, sleep_sec):
    async def runner():
        await asyncio.sleep(max(3, sleep_sec))
        if (cur := currently_playing.get(chat_id)) and cur.get('id') == song_id:
            await play_next_song(chat_id, from_auto=True)
    return asyncio.create_task(runner())

async def safe_play(c, u): await calls.play(c, MediaStream(u, audio_parameters=AudioQuality.HIGH))
async def safe_change(c, u): await calls.change_stream(c, MediaStream(u, audio_parameters=AudioQuality.HIGH))
async def safe_leave(c): await calls.leave_group_call(c)
async def safe_pause(c): await calls.pause_stream(c)
async def safe_resume(c): await calls.resume_stream(c)

# <<< MODIFIED SECTION: ADVANCED KEYBOARD AND CALLBACKS >>>

def music_controls_keyboard(chat_id: int, is_paused: bool = False, song_url: str = ""):
    """Creates the dynamic inline keyboard for music controls."""
    play_pause = InlineKeyboardButton("▶️ استئناف" if is_paused else "⏸️ إيقاف مؤقت", callback_data=f"{'resume' if is_paused else 'pause'}_{chat_id}")
    row1 = [play_pause, InlineKeyboardButton("⏭️ تخطي", callback_data=f"skip_{chat_id}"), InlineKeyboardButton("⏹️ إيقاف", callback_data=f"stop_{chat_id}")]
    row2 = []
    if song_url: row2.append(InlineKeyboardButton("🔗 رابط الأغنية", url=song_url))
    row2.append(InlineKeyboardButton("🔔 القناة", url=CHANNEL_URL))
    return InlineKeyboardMarkup([row1, row2])

@bot.on_callback_query(filters.regex(r"^(pause|resume|skip|stop)_"))
async def callback_handler(_, query: CallbackQuery):
    """Handles all music control button presses."""
    try:
        command, chat_id_str = query.data.split("_", 1)
        chat_id = int(chat_id_str)
    except ValueError: return await query.answer("Callback error.", show_alert=True)

    cur = currently_playing.get(chat_id)

    if command == "pause":
        if not cur or cur.get('_paused_at'): return await query.answer("متوقف بالفعل.", show_alert=False)
        try:
            await safe_pause(chat_id)
            cancel_timer(chat_id)
            cur['_paused_at'] = time.time()
            await query.answer("تم الإيقاف المؤقت.")
            await query.edit_message_reply_markup(music_controls_keyboard(chat_id, True, cur.get('webpage_url')))
        except Exception as e: await query.answer(f"❌ فشل: {e}", show_alert=True)

    elif command == "resume":
        if not cur or not cur.get('_paused_at'): return await query.answer("يعمل بالفعل.", show_alert=False)
        try:
            await safe_resume(chat_id)
            paused_for = time.time() - cur['_paused_at']
            cur['_started_at'] += paused_for
            cur['_paused_at'] = None
            elapsed = time.time() - cur['_started_at']
            remaining = max(3, cur['duration'] - elapsed)
            set_timer(chat_id, create_playback_timer(chat_id, cur.get('id', ''), remaining + 1))
            await query.answer("تم الاستئناف.")
            await query.edit_message_reply_markup(music_controls_keyboard(chat_id, False, cur.get('webpage_url')))
        except Exception as e: await query.answer(f"❌ فشل: {e}", show_alert=True)

    elif command == "skip":
        if not cur: return await query.answer("لا يوجد شيء لتخطيه.", show_alert=True)
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
            await query.edit_message_caption(f"⏹️ **تم إيقاف التشغيل بواسطة {query.from_user.mention}**\n🎵 `{title}`", reply_markup=None)
        except: # In case it was a text message
            await query.edit_message_text(f"⏹️ **تم إيقاف التشغيل بواسطة {query.from_user.mention}**\n🎵 `{title}`", reply_markup=None, disable_web_page_preview=True)

async def play_next_song(chat_id: int, from_skip: bool = False, user_mention: str = "تلقائي", from_auto: bool = False):
    """Plays the next song in the queue and sends the control interface."""
    if not music_queue.get(chat_id):
        if not from_auto: await bot.send_message(chat_id, "📭 انتهت قائمة الانتظار.")
        await safe_leave(chat_id)
        if chat_id in currently_playing: del currently_playing[chat_id]
        return

    song = music_queue[chat_id].pop(0)
    try:
        stream_method = safe_change if currently_playing.get(chat_id) else safe_play
        await stream_method(chat_id, song['url'])
        
        song.update({'_started_at': time.time(), '_paused_at': None})
        currently_playing[chat_id] = song
        
        if (dur := int(song.get('duration', 0))) > 0:
            set_timer(chat_id, create_playback_timer(chat_id, song.get('id', ''), dur + 2))

        keyboard = music_controls_keyboard(chat_id, False, song.get('webpage_url'))
        caption = f"⏭️ **تم التخطي بواسطة {user_mention}**\n\n" if from_skip else ""
        caption += f"▶️ **يتم التشغيل الآن**\n🎵 `{song['title']}`\n⏱️ {format_duration(dur)}\n👤 {song['uploader']}"
        
        if song.get('thumbnail'):
            await bot.send_photo(chat_id, song['thumbnail'], caption=caption, reply_markup=keyboard)
        else:
            await bot.send_message(chat_id, caption, reply_markup=keyboard, disable_web_page_preview=True)
            
    except Exception as e:
        logger.error(f"❌ Playback error in {chat_id}: {e}")
        await bot.send_message(chat_id, f"❌ خطأ أثناء التشغيل: {e}")
        await play_next_song(chat_id) # Attempt to play the next song in queue

# ========================= Commands =========================
@bot.on_message(filters.command(["play", "p"]) & (filters.group | filters.channel))
async def play_cmd(_, message: Message):
    if not pytgcalls_available: return await message.reply("❌ **التشغيل غير متاح حالياً.**")
    
    chat_id = await resolve_target_chat_id(message.chat)
    query = " ".join(message.command[1:])
    if not query: return await message.reply("🤔 ماذا تريد أن أُشغل؟")

    msg = await message.reply_text("🔄 **جاري التحضير...**")
    if not currently_playing.get(chat_id) and not await join_chat(chat_id, message):
        return await msg.edit("❌ فشل انضمام المساعد.")

    await msg.edit("🔍 **جاري البحث...**")
    song_info = await download_song(query)
    if not song_info: return await msg.edit("❌ لم أجد الأغنية!")

    if chat_id not in music_queue: music_queue[chat_id] = []
    music_queue[chat_id].append(song_info)
    
    if not currently_playing.get(chat_id):
        await msg.delete()  # <<< SMOOTH UX: DELETE STATUS MESSAGE
        await play_next_song(chat_id)
    else:
        await msg.edit(f"✅ **أُضيفت للقائمة #{len(music_queue[chat_id])}**\n🎵 `{song_info['title']}`")

# Other text-based commands
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(_, m: Message): await m.reply("أهلاً بك! أضفني إلى مجموعة وابدأ التشغيل.")

@bot.on_message(filters.command("skip"))
async def skip_cmd(_, m: Message):
    chat_id = await resolve_target_chat_id(m.chat)
    if not currently_playing.get(chat_id): return await m.reply("❌ لا يوجد شيء لتخطيه.")
    await play_next_song(chat_id, from_skip=True, user_mention=m.from_user.mention)

@bot.on_message(filters.command("stop"))
async def stop_cmd(_, m: Message):
    chat_id = await resolve_target_chat_id(m.chat)
    if not currently_playing.get(chat_id): return await m.reply("🤷 لا يوجد شيء لإيقافه.")
    cancel_timer(chat_id); await safe_leave(chat_id)
    if chat_id in music_queue: music_queue[chat_id] = []
    if chat_id in currently_playing: del currently_playing[chat_id]
    await m.reply(f"⏹️ **تم إيقاف التشغيل بواسطة {m.from_user.mention}**")

# ========================= Web Server & Main Execution =========================
async def start_web():
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="Bot is running"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()
    logger.info(f"✅ Web server started on port {PORT}")

async def main():
    global bot_username
    logger.info("Initializing application...")
    
    # We keep the working startup sequence
    if userbot_available:
        await userbot.start()
        me_user = await userbot.get_me()
        logger.info(f"✅ UserBot {me_user.first_name} started.")
        if pytgcalls_available:
            await calls.start()
            logger.info("✅ PyTgCalls session started.")

    await bot.start()
    me_bot = await bot.get_me()
    bot_username = me_bot.username
    logger.info(f"✅ Bot @{bot_username} started.")
    
    await start_web()
    logger.info("🚀 Application is fully running!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    bot.run(main())
