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
ASSISTANT_USERNAME = os.getenv("ASSISTANT_USERNAME")

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

# ========================= FFmpeg & PyTgCalls Setup =========================
# This section is kept from the previous version but omitted here for brevity
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

# ========================= State =========================
stats = { 'songs_played': 0, 'start_time': time.time() }
music_queue: Dict[int, List[Dict]] = {}
currently_playing: Dict[int, Dict] = {}
bot_username = None
playback_timers: Dict[int, asyncio.Task] = {}

# ========================= Helper Functions =========================
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
        if chat_obj.username:
            await userbot.join_chat(chat_obj.username)
        else: # Private group/channel
            invite_link = await bot.export_chat_invite_link(chat_id)
            await userbot.join_chat(invite_link)
        return True
    except UserAlreadyParticipant: return True
    except Exception as e:
        logger.error(f"Join chat error in {chat_id}: {e}")
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
        if cur and cur.get('id') == song_id:
            await play_next_song(chat_id, from_auto=True)
    return asyncio.create_task(runner())

# PyTgCalls Wrappers
async def safe_play(chat_id, url): await calls.play(chat_id, MediaStream(url, audio_parameters=AudioQuality.HIGH))
async def safe_change_stream(chat_id, url): await calls.change_stream(chat_id, MediaStream(url, audio_parameters=AudioQuality.HIGH))
async def safe_leave(chat_id): await calls.leave_group_call(chat_id)
async def safe_pause(chat_id): await calls.pause_stream(chat_id)
async def safe_resume(chat_id): await calls.resume_stream(chat_id)

# ========================= Music Controls & Callbacks =========================
def music_controls_keyboard(chat_id: int, is_paused: bool = False, song_url: str = ""):
    play_pause_button = InlineKeyboardButton(
        "▶️ استئناف" if is_paused else "⏸️ إيقاف مؤقت",
        callback_data=f"{'resume' if is_paused else 'pause'}_{chat_id}"
    )
    row1 = [
        play_pause_button,
        InlineKeyboardButton("⏭️ تخطي", callback_data=f"skip_{chat_id}"),
        InlineKeyboardButton("⏹️ إيقاف", callback_data=f"stop_{chat_id}")
    ]
    row2 = []
    if song_url: row2.append(InlineKeyboardButton("🔗 الرابط", url=song_url))
    row2.append(InlineKeyboardButton("🔔 القناة", url="https://t.me/RosaliaChannel")) # Example channel
    
    return InlineKeyboardMarkup([row1, row2])

@bot.on_callback_query(filters.regex(r"^(pause|resume|skip|stop)_"))
async def controls_callback_handler(client: Client, query: CallbackQuery):
    try:
        command, chat_id_str = query.data.split("_", 1)
        chat_id = int(chat_id_str)
    except ValueError:
        return await query.answer("خطأ في البيانات.", show_alert=True)

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
            await query.edit_message_caption(
                caption=f"⏹️ **تم إيقاف التشغيل بواسطة {query.from_user.mention}**\n🎵 `{title}`",
                reply_markup=None
            )
        except: # If it was a text message
            await query.edit_message_text(
                f"⏹️ **تم إيقاف التشغيل بواسطة {query.from_user.mention}**\n🎵 `{title}`",
                reply_markup=None, disable_web_page_preview=True
            )

# ========================= Core Playback =========================
async def play_next_song(chat_id: int, from_skip: bool = False, from_auto: bool = False, user_mention: str = "تلقائي"):
    if chat_id not in music_queue or not music_queue[chat_id]:
        await safe_leave(chat_id)
        if chat_id in currently_playing: del currently_playing[chat_id]
        if not from_auto:
            try: await bot.send_message(chat_id, "📭 انتهت قائمة الانتظار. سأغادر المكالمة.")
            except: pass
        return

    next_song = music_queue[chat_id].pop(0)

    try:
        if currently_playing.get(chat_id):
            await safe_change_stream(chat_id, next_song['url'])
        else:
            await safe_play(chat_id, next_song['url'])
        
        next_song.update({'_started_at': time.time(), '_paused_at': None})
        currently_playing[chat_id] = next_song
        stats['songs_played'] += 1
        
        dur = int(next_song.get('duration', 0))
        if dur > 0: set_timer(chat_id, create_playback_timer(chat_id, next_song.get('id', ''), dur + 2))

        keyboard = music_controls_keyboard(chat_id, is_paused=False, song_url=next_song.get('webpage_url'))
        
        caption = f"⏭️ **تم التخطي بواسطة {user_mention}**\n\n" if from_skip else ""
        caption += (
            f"▶️ **يتم التشغيل الآن**\n"
            f"🎵 **العنوان:** `{next_song['title']}`\n"
            f"⏱️ **المدة:** {format_duration(dur)}\n"
            f"👤 **القناة:** {next_song['uploader']}"
        )
        
        send_method = bot.send_photo if next_song.get('thumbnail') else bot.send_message
        params = {'chat_id': chat_id, 'caption': caption, 'reply_markup': keyboard}
        if next_song.get('thumbnail'): params['photo'] = next_song['thumbnail']
        else: params['disable_web_page_preview'] = True
        
        await send_method(**params)

    except Exception as e:
        logger.error(f"❌ Play error in chat {chat_id}: {e}")
        await bot.send_message(chat_id, f"❌ حدث خطأ أثناء التشغيل: {e}")
        await play_next_song(chat_id) # Try next one

# ========================= Commands =========================
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(_, message: Message):
    await message.reply_photo(
        photo="https://telegra.ph/file/028c297544f8f7457a44f.jpg",
        caption=f"🎵 **أهلاً بك، {message.from_user.mention}!**\n\nأنا بوت روزاليا لتشغيل الموسيقى في المجموعات والقنوات.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ أضفني إلى مجموعتك", url=f"https://t.me/{bot_username}?startgroup=true")],
            [InlineKeyboardButton("📚 الأوامر", callback_data="help_page")]
        ])
    )

@bot.on_message(filters.command(["play", "p"]) & (filters.group | filters.channel))
async def play_cmd(client: Client, message: Message):
    chat_id = await resolve_target_chat_id(message.chat)
    if not userbot_available or not pytgcalls_available:
        return await message.reply("❌ **التشغيل الفعلي غير متاح!** (لم يتم توفير `SESSION_STRING`)")

    query = " ".join(message.command[1:])
    if not query:
        return await message.reply("🤔 ماذا تريد أن أُشغل؟ يرجى إعطاء اسم الأغنية أو رابط.")

    msg = await message.reply_text("🔄 **جاري التحضير...**")

    if not currently_playing.get(chat_id) and not await join_chat(chat_id, invoker=message):
        return await msg.edit("❌ فشل انضمام المساعد. لا يمكن المتابعة.")

    await msg.edit("🔍 **جاري البحث عن الأغنية...**")
    song_info = await download_song(query)
    if not song_info:
        return await msg.edit("❌ لم أجد الأغنية المطلوبة!")

    if chat_id not in music_queue:
        music_queue[chat_id] = []
    
    music_queue[chat_id].append(song_info)
    position = len(music_queue[chat_id])

    # <<< MODIFIED SECTION >>>
    if chat_id not in currently_playing:
        # 1. Delete the temporary status message ("Searching...")
        await msg.delete()
        # 2. Start playback (this function will send the new interface)
        await play_next_song(chat_id)
    else:
        # If a song is already playing, edit the message to confirm addition to the queue
        await msg.edit(
            f"✅ **تمت الإضافة للقائمة #{position}**\n\n"
            f"🎵 `{song_info['title']}`\n"
            f"⏱️ {format_duration(song_info.get('duration'))}"
        )
    # <<< END OF MODIFIED SECTION >>>

# ... (Other commands like /skip, /stop, /queue) ...
@bot.on_message(filters.command("skip") & (filters.group | filters.channel))
async def skip_cmd(_, message: Message):
    chat_id = await resolve_target_chat_id(message.chat)
    if not currently_playing.get(chat_id): return await message.reply("❌ لا يوجد شيء لتخطيه.")
    await play_next_song(chat_id, from_skip=True, user_mention=message.from_user.mention)

@bot.on_message(filters.command("stop") & (filters.group | filters.channel))
async def stop_cmd(_, message: Message):
    chat_id = await resolve_target_chat_id(message.chat)
    cancel_timer(chat_id)
    await safe_leave(chat_id)
    if chat_id in music_queue: music_queue[chat_id] = []
    if chat_id in currently_playing: del currently_playing[chat_id]
    await message.reply(f"⏹️ تم إيقاف التشغيل بواسطة {message.from_user.mention}")

# ========================= Main Execution =========================
async def main():
    global bot_username
    logger.info("Starting bot...")
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
    
    logger.info("Bot is now running!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot shutting down...")
