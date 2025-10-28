import os
import re
import base64
import logging
import asyncio
import time
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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/RosaliaChannel")

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
        logger.error(f"UserBot init error: {e}")
        userbot = None
else:
    logger.warning("⚠️ No SESSION_STRING provided. Music playback will not be available.")

# ========================= Compat Patch =========================
try:
    import pyrogram.errors as _p_err
    if not hasattr(_p_err, "GroupcallForbidden"):
        class GroupcallForbidden(_p_err.RPCError if hasattr(_p_err, "RPCError") else Exception):
            ID = "GROUPCALL_FORBIDDEN"
            def __init__(self, *args, **kwargs):
                super().__init__("The user is not allowed to join the group call")
        _p_err.GroupcallForbidden = GroupcallForbidden
        logger.info("🩹 Applied compat patch for GroupcallForbidden.")
except Exception as _e:
    logger.warning(f"Compat patch failed: {_e}")

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
    except ImportError:
        logger.error("❌ pytgcalls is not installed. Playback disabled.")
    except Exception as e:
        logger.error(f"❌ pytgcalls init error: {e}")

# ... (All other functions like format_duration, download_song, controls, playback, etc. remain the same) ...
# Omitted for brevity, they are correct from the previous version.
stats = { 'songs_played': 0 }
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
    ydl_opts = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True, 'default_search': 'ytsearch'}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if 'entries' in info: info = info['entries'][0]
        return {
            'id': info.get('id', ''), 'title': info.get('title', 'Unknown'),
            'url': info.get('url'), 'duration': info.get('duration', 0),
            'thumbnail': info.get('thumbnail', ''), 'webpage_url': info.get('webpage_url', ''),
            'uploader': info.get('uploader', 'Unknown'),
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
            invite_link = await bot.export_chat_invite_link(chat_id)
            await userbot.join_chat(invite_link)
        return True
    except UserAlreadyParticipant: return True
    except Exception as e:
        if invoker: await invoker.reply(f"❌ فشل انضمام المساعد. خطأ: {e}")
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

def music_controls_keyboard(chat_id, is_paused=False, song_url=""):
    row1 = [InlineKeyboardButton("▶️ استئناف" if is_paused else "⏸️ إيقاف مؤقت", f"{'resume' if is_paused else 'pause'}_{chat_id}"),
            InlineKeyboardButton("⏭️ تخطي", f"skip_{chat_id}"), InlineKeyboardButton("⏹️ إيقاف", f"stop_{chat_id}")]
    row2 = []
    if song_url: row2.append(InlineKeyboardButton("🔗 الرابط", url=song_url))
    row2.append(InlineKeyboardButton("🔔 القناة", url=CHANNEL_URL))
    return InlineKeyboardMarkup([row1, row2])

@bot.on_callback_query(filters.regex(r"^(pause|resume|skip|stop)_"))
async def cb_handler(_, query):
    try:
        cmd, cid_str = query.data.split("_", 1)
        cid = int(cid_str)
    except: return
    cur = currently_playing.get(cid)
    if cmd == "pause":
        if not cur or cur.get('_paused_at'): return await query.answer("متوقف.", show_alert=False)
        try:
            await safe_pause(cid); cancel_timer(cid); cur['_paused_at'] = time.time()
            await query.answer("تم الإيقاف المؤقت.")
            await query.edit_message_reply_markup(music_controls_keyboard(cid, True, cur.get('webpage_url')))
        except Exception as e: await query.answer(f"❌: {e}", True)
    elif cmd == "resume":
        if not cur or not cur.get('_paused_at'): return await query.answer("يعمل.", show_alert=False)
        try:
            await safe_resume(cid)
            pd = time.time() - cur['_paused_at']; cur['_started_at'] += pd; cur['_paused_at'] = None
            el = time.time() - cur['_started_at']; rem = max(3, cur['duration'] - el)
            set_timer(cid, create_playback_timer(cid, cur.get('id', ''), rem + 1))
            await query.answer("تم الاستئناف.")
            await query.edit_message_reply_markup(music_controls_keyboard(cid, False, cur.get('webpage_url')))
        except Exception as e: await query.answer(f"❌: {e}", True)
    elif cmd == "skip":
        await query.answer("جارٍ التخطي...")
        await query.message.delete()
        await play_next_song(cid, True, query.from_user.mention)
    elif cmd == "stop":
        await query.answer("جارٍ الإيقاف...")
        cancel_timer(cid); await safe_leave(cid)
        title = cur['title'] if cur else "..."
        if cid in currently_playing: del currently_playing[cid]
        if cid in music_queue: music_queue[cid] = []
        try:
            await query.edit_message_caption(f"⏹️ **تم إيقاف التشغيل بواسطة {query.from_user.mention}**\n🎵 `{title}`", reply_markup=None)
        except: await query.edit_message_text(f"⏹️ **تم إيقاف التشغيل بواسطة {query.from_user.mention}**\n🎵 `{title}`", reply_markup=None)

async def play_next_song(chat_id, from_skip=False, user_mention="تلقائي", from_auto=False):
    if not music_queue.get(chat_id):
        if not from_auto: await bot.send_message(chat_id, "📭 انتهت القائمة.")
        await safe_leave(chat_id)
        if chat_id in currently_playing: del currently_playing[chat_id]
        return
    song = music_queue[chat_id].pop(0)
    try:
        await (safe_change if currently_playing.get(chat_id) else safe_play)(chat_id, song['url'])
        song.update({'_started_at': time.time(), '_paused_at': None}); currently_playing[chat_id] = song
        stats['songs_played'] += 1
        if (dur := int(song.get('duration', 0))) > 0: set_timer(chat_id, create_playback_timer(chat_id, song.get('id'), dur + 2))
        cap = f"⏭️ **تخطي بواسطة {user_mention}**\n\n" if from_skip else ""
        cap += f"▶️ **يتم التشغيل**\n🎵 `{song['title']}`\n⏱️ {format_duration(dur)}\n👤 {song['uploader']}"
        kb = music_controls_keyboard(chat_id, False, song.get('webpage_url'))
        if song.get('thumbnail'): await bot.send_photo(chat_id, song['thumbnail'], cap, reply_markup=kb)
        else: await bot.send_message(chat_id, cap, reply_markup=kb, disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"❌ Play error in {chat_id}: {e}")
        await bot.send_message(chat_id, f"❌ خطأ: {e}")
        await play_next_song(chat_id)

@bot.on_message(filters.command(["play", "p"]) & (filters.group | filters.channel))
async def play_cmd(_, message):
    cid = await resolve_target_chat_id(message.chat)
    if not pytgcalls_available: return await message.reply("❌ **التشغيل غير متاح.**")
    query = " ".join(message.command[1:])
    if not query: return await message.reply("🤔 ماذا تريد أن أُشغل؟")
    msg = await message.reply_text("🔄 **جاري التحضير...**")
    if not currently_playing.get(cid) and not await join_chat(cid, message):
        return await msg.edit("❌ فشل انضمام المساعد.")
    await msg.edit("🔍 **جاري البحث...**")
    song = await download_song(query)
    if not song: return await msg.edit("❌ لم أجد الأغنية!")
    if cid not in music_queue: music_queue[cid] = []
    music_queue[cid].append(song)
    if not currently_playing.get(cid):
        await msg.delete()
        await play_next_song(cid)
    else: await msg.edit(f"✅ **أُضيفت للقائمة #{len(music_queue[cid])}**\n🎵 `{song['title']}`")

@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(_, m): await m.reply("أهلاً بك! أضفني لمجموعة وابدأ التشغيل.")


# ========================= Web Server & Main Execution =========================
# <<< START OF MODIFIED SECTION: BACKGROUND WEB SERVER >>>
async def run_web_server():
    """
    Starts the aiohttp web server as a background task.
    """
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="Bot is running"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    try:
        await site.start()
        logger.info(f"✅ Web server started successfully on port {PORT}.")
    except Exception as e:
        logger.error(f"❌ Failed to start web server: {e}")

async def main():
    global bot_username
    
    # Create a background task for the web server
    web_server_task = asyncio.create_task(run_web_server())

    logger.info("Initializing Telegram clients...")
    
    # Start all clients concurrently
    clients = [bot]
    if userbot_available:
        clients.append(userbot)
    
    await asyncio.gather(*[client.start() for client in clients])

    # Get bot info
    me_bot = await bot.get_me()
    bot_username = me_bot.username
    logger.info(f"✅ Bot @{bot_username} started.")

    # Get userbot info if available
    if userbot_available:
        me_user = await userbot.get_me()
        logger.info(f"✅ UserBot {me_user.first_name} started.")
        if pytgcalls_available:
            await calls.start()
            logger.info("✅ PyTgCalls started.")

    logger.info("🚀 Bot is fully operational!")
    
    # Keep the main task running forever
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot shutting down...")
# <<< END OF MODIFIED SECTION >>>
