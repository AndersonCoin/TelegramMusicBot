import os
import logging
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserAlreadyParticipant, ChatAdminRequired, UserNotParticipant
from dotenv import load_dotenv
from aiohttp import web
import yt_dlp
from typing import Dict, List
import time

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
PORT = int(os.getenv("PORT", 10000))

# ========================= Clients =========================
bot = Client("bot", api_id=int(API_ID), api_hash=API_HASH, bot_token=BOT_TOKEN)

userbot_available = False
if SESSION_STRING:
    try:
        userbot = Client("userbot", api_id=int(API_ID), api_hash=API_HASH, session_string=SESSION_STRING)
        userbot_available = True
        logger.info("✅ UserBot configured")
    except Exception as e:
        logger.error(f"UserBot error: {e}")
        userbot = None
else:
    userbot = None

# ========================= Compat Patch (fix GroupcallForbidden import) =========================
# بعض إصدارات pytgcalls تحاول import GroupcallForbidden من pyrogram.errors وهو غير موجود في Pyrogram 2.x
try:
    import pyrogram.errors as _p_err
    if not hasattr(_p_err, "GroupcallForbidden"):
        class GroupcallForbidden(_p_err.RPCError if hasattr(_p_err, "RPCError") else Exception):
            def __init__(self, *args, **kwargs):
                super().__init__("GroupcallForbidden")
        _p_err.GroupcallForbidden = GroupcallForbidden
        logger.info("🩹 Applied compat patch: pyrogram.errors.GroupcallForbidden")
except Exception as _e:
    logger.warning(f"Compat patch failed: {_e}")

# ========================= PyTgCalls setup (version-agnostic) =========================
pytgcalls_available = False
calls = None
HAVE_MEDIA_STREAM = False  # هل واجهة MediaStream متاحة؟

if userbot_available:
    try:
        from pytgcalls import PyTgCalls
        calls = PyTgCalls(userbot)

        # جرّب استيراد واجهة MediaStream/AudioQuality (قد لا تكون متوفرة في بعض الإصدارات)
        try:
            from pytgcalls.types import MediaStream, AudioQuality  # type: ignore
            HAVE_MEDIA_STREAM = True
        except Exception:
            HAVE_MEDIA_STREAM = False

        pytgcalls_available = True
        logger.info("✅ pytgcalls imported successfully")
    except Exception as e:
        logger.error(f"❌ pytgcalls error: {e}")

# ========================= State =========================
stats = {
    'messages': 0, 'commands': 0, 'users': set(), 'groups': set(),
    'songs_searched': 0, 'songs_played': 0, 'start_time': time.time()
}
music_queue: Dict[int, List[Dict]] = {}
currently_playing: Dict[int, Dict] = {}
bot_username = None

# ========================= YouTube =========================
ydl_opts = {
    'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True,
    'no_warnings': True, 'extract_flat': False, 'geo_bypass': True, 'ignoreerrors': True,
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

        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, extract)
        if not info:
            return None

        return {
            'title': info.get('title', 'Unknown'),
            'url': info.get('url'),
            'duration': info.get('duration', 0),
            'thumbnail': info.get('thumbnail', ''),
            'webpage_url': info.get('webpage_url', ''),
            'uploader': info.get('uploader', 'Unknown'),
            'view_count': info.get('view_count', 0),
            'like_count': info.get('like_count', 0)
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

# ========================= Auto-Join Helper =========================
async def join_chat(chat_id: int):
    if not userbot_available:
        return False
    try:
        try:
            await userbot.get_chat_member(chat_id, "me")
            return True
        except UserNotParticipant:
            pass

        chat = await bot.get_chat(chat_id)

        if getattr(chat, "username", None):
            try:
                await userbot.join_chat(chat.username)
                return True
            except Exception:
                pass

        try:
            invite_link = await bot.export_chat_invite_link(chat_id)
            await userbot.join_chat(invite_link)
            return True
        except Exception:
            return False

    except UserAlreadyParticipant:
        return True
    except Exception as e:
        logger.error(f"Join error: {e}")
        return False

# ========================= PyTgCalls Safe Wrappers =========================
async def safe_play(chat_id: int, url: str):
    # حديث: MediaStream + AudioQuality
    if HAVE_MEDIA_STREAM and hasattr(globals().get('MediaStream', object), '__call__'):
        return await calls.play(chat_id, MediaStream(url, audio_parameters=AudioQuality.HIGH))  # type: ignore
    # قديم: تمرير الرابط مباشرة
    return await calls.play(chat_id, url)

async def safe_change_stream(chat_id: int, url: str):
    if hasattr(calls, 'change_stream'):
        if HAVE_MEDIA_STREAM and hasattr(globals().get('MediaStream', object), '__call__'):
            return await calls.change_stream(chat_id, MediaStream(url, audio_parameters=AudioQuality.HIGH))  # type: ignore
        return await calls.change_stream(chat_id, url)
    # إن لم تتوفر change_stream، استخدم play كحل بديل
    return await safe_play(chat_id, url)

async def safe_leave(chat_id: int):
    if hasattr(calls, 'leave_call'):
        return await calls.leave_call(chat_id)
    if hasattr(calls, 'leave_group_call'):
        return await calls.leave_group_call(chat_id)

async def safe_pause(chat_id: int):
    if hasattr(calls, 'pause_stream'):
        return await calls.pause_stream(chat_id)

async def safe_resume(chat_id: int):
    if hasattr(calls, 'resume_stream'):
        return await calls.resume_stream(chat_id)

# ========================= Core Playback =========================
async def play_next_song(chat_id: int):
    if not pytgcalls_available or not calls:
        return False

    if chat_id not in music_queue or not music_queue[chat_id]:
        try:
            await safe_leave(chat_id)
            if chat_id in currently_playing:
                del currently_playing[chat_id]
            await bot.send_message(chat_id, "📭 انتهت القائمة")
        except Exception:
            pass
        return False

    next_song = music_queue[chat_id].pop(0)

    try:
        await safe_play(chat_id, next_song['url'])
        currently_playing[chat_id] = next_song
        stats['songs_played'] += 1
        logger.info(f"▶️ Playing: {next_song['title']}")

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("⏸️", callback_data="pause"),
            InlineKeyboardButton("⏭️", callback_data="skip"),
            InlineKeyboardButton("⏹️", callback_data="stop")
        ]])

        await bot.send_message(
            chat_id,
            f"▶️ **يتم التشغيل:**\n🎵 {next_song['title']}",
            reply_markup=keyboard
        )
        return True

    except Exception as e:
        msg = str(e).lower()
        logger.error(f"❌ Play error: {msg}")

        if "no active group call" in msg or "group_call_invalid" in msg or "groupcall" in msg:
            await bot.send_message(chat_id, "❌ **لا توجد محادثة صوتية نشطة!**")
            return False

        if "already" in msg or "joined" in msg or "in call" in msg or "already joined" in msg:
            try:
                await safe_change_stream(chat_id, next_song['url'])
                currently_playing[chat_id] = next_song
                stats['songs_played'] += 1
                await bot.send_message(chat_id, f"▶️ **تغيير إلى:**\n🎵 {next_song['title']}")
                return True
            except Exception as e2:
                logger.error(f"❌ Change stream error: {e2}")
                return await play_next_song(chat_id)

        return await play_next_song(chat_id)

# Handler for stream end (signature-agnostic)
if pytgcalls_available and calls:
    @calls.on_stream_end()
    async def on_stream_end_handler(*args, **kwargs):
        """
        بعض الإصدارات تُمرّر chat_id مباشرة، وأخرى تمرّر Update له خاصية chat_id.
        نحاول استخراج chat_id من جميع الأشكال.
        """
        chat_id = None

        if 'chat_id' in kwargs:
            chat_id = kwargs.get('chat_id')
        else:
            for a in args:
                if isinstance(a, int):
                    chat_id = a
                    break
                if hasattr(a, 'chat_id'):
                    chat_id = getattr(a, 'chat_id', None)
                    if chat_id is not None:
                        break

        if chat_id is None:
            logger.warning("⚠️ on_stream_end: لم أستطع تحديد chat_id")
            return

        try:
            if chat_id in currently_playing:
                await bot.send_message(chat_id, f"✅ **انتهى:** {currently_playing[chat_id]['title']}")
            await play_next_song(chat_id)
        except Exception as e:
            logger.error(f"Stream end handler error: {e}")

# ========================= Commands =========================
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message: Message):
    stats['messages'] += 1
    stats['users'].add(message.from_user.id)
    await message.reply_text(
        f"🎵 **مرحباً {message.from_user.mention}!**\n\n"
        f"أنا بوت تشغيل موسيقى للقنوات والمجموعات.\n\n"
        f"**الحالة:** {'✅ التشغيل الفعلي متاح' if (userbot_available and pytgcalls_available) else '⚠️ معلومات فقط'}\n\n"
        f"**للبدء:**\n"
        f"1. أضفني لمجموعتك كمشرف\n"
        f"2. ابدأ محادثة صوتية\n"
        f"3. استخدم `/play [أغنية]`"
    )

@bot.on_message(filters.command("help"))
async def help_cmd(client, message: Message):
    stats['messages'] += 1
    await message.reply_text(
        "📚 **الأوامر:**\n\n"
        "• `/play [أغنية]` - تشغيل/إضافة\n"
        "• `/pause` - إيقاف مؤقت\n"
        "• `/resume` - استئناف\n"
        "• `/skip` - تخطي\n"
        "• `/stop` - إيقاف كامل\n"
        "• `/queue` - القائمة\n"
        "• `/ping` - الحالة"
    )

@bot.on_message(filters.command("ping"))
async def ping_cmd(client, message: Message):
    stats['messages'] += 1
    start = time.time()
    msg = await message.reply_text("🏓")
    end = time.time()
    await msg.edit(
        f"🏓 **Pong!**\n\n"
        f"⚡ `{round((end-start)*1000, 2)}ms`\n"
        f"🤖 Bot: ✅\n"
        f"👤 UserBot: {'✅' if userbot_available else '❌'}\n"
        f"🎵 PyTgCalls: {'✅' if pytgcalls_available else '❌'}\n"
        f"▶️ Playing: {len(currently_playing)}"
    )

@bot.on_message(filters.command(["play", "p"]) & (filters.group | filters.channel))
async def play_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    stats['groups'].add(message.chat.id)

    if not userbot_available or not pytgcalls_available:
        return await message.reply_text("❌ **التشغيل الفعلي غير متاح!**")

    if len(message.command) < 2:
        return await message.reply_text("❌ استخدم: `/play [اسم الأغنية]`")

    query = " ".join(message.command[1:])
    chat_id = message.chat.id

    msg = await message.reply_text("🔄 جاري التحضير...")

    if not await join_chat(chat_id):
        return await msg.edit("❌ فشل انضمام العميل المساعد!")

    await msg.edit("🔍 البحث...")
    song_info = await download_song(query)
    if not song_info:
        return await msg.edit("❌ لم أجد الأغنية!")

    if chat_id not in music_queue:
        music_queue[chat_id] = []

    music_queue[chat_id].append(song_info)
    position = len(music_queue[chat_id])

    if chat_id not in currently_playing:
        await msg.edit("🎵 بدء التشغيل...")
        if not await play_next_song(chat_id):
            await msg.delete()
    else:
        await msg.edit(
            f"✅ **إضافة للقائمة #{position}**\n\n"
            f"🎵 {song_info['title']}\n"
            f"⏱️ {format_duration(song_info['duration'])}"
        )

@bot.on_message(filters.command("pause") & (filters.group | filters.channel))
async def pause_cmd(client, message: Message):
    stats['messages'] += 1
    if not pytgcalls_available:
        return
    try:
        await safe_pause(message.chat.id)
        await message.reply_text("⏸️ توقف مؤقت")
    except Exception as e:
        await message.reply_text(f"❌ {e}")

@bot.on_message(filters.command("resume") & (filters.group | filters.channel))
async def resume_cmd(client, message: Message):
    stats['messages'] += 1
    if not pytgcalls_available:
        return
    try:
        await safe_resume(message.chat.id)
        await message.reply_text("▶️ استئناف")
    except Exception as e:
        await message.reply_text(f"❌ {e}")

@bot.on_message(filters.command("skip") & (filters.group | filters.channel))
async def skip_cmd(client, message: Message):
    stats['messages'] += 1
    if message.chat.id not in currently_playing:
        return await message.reply_text("❌ لا يوجد شيء لتخطيه")
    await message.reply_text(f"⏭️ تخطي: {currently_playing[message.chat.id]['title']}")
    await play_next_song(message.chat.id)

@bot.on_message(filters.command("stop") & (filters.group | filters.channel))
async def stop_cmd(client, message: Message):
    stats['messages'] += 1
    chat_id = message.chat.id
    try:
        if pytgcalls_available:
            await safe_leave(chat_id)
        if chat_id in music_queue:
            music_queue[chat_id] = []
        if chat_id in currently_playing:
            del currently_playing[chat_id]
        await message.reply_text("⏹️ تم الإيقاف")
    except Exception as e:
        await message.reply_text(f"❌ {e}")

@bot.on_message(filters.command("queue") & (filters.group | filters.channel))
async def queue_cmd(client, message: Message):
    stats['messages'] += 1
    chat_id = message.chat.id
    text = ""

    if chat_id in currently_playing:
        text += f"▶️ {currently_playing[chat_id]['title']}\n\n"

    if chat_id in music_queue and music_queue[chat_id]:
        text += "📋 القائمة:\n"
        for i, s in enumerate(music_queue[chat_id][:10], 1):
            text += f"{i}. {s['title']}\n"

    await message.reply_text(text or "📭 فارغة")

# ========================= Callback =========================
@bot.on_callback_query()
async def callback_handler(client, query: CallbackQuery):
    data = query.data
    await query.answer()

    if data == "help":
        await help_cmd(client, query.message)
    elif data == "pause":
        await pause_cmd(client, query.message)
    elif data == "resume":
        await resume_cmd(client, query.message)
    elif data == "skip":
        await skip_cmd(client, query.message)
    elif data == "stop":
        await stop_cmd(client, query.message)
    elif data == "queue":
        await queue_cmd(client, query.message)

# ========================= Web Server =========================
async def health(request):
    return web.Response(text="OK")

async def index(request):
    html = f"""
<html><body style="font-family:Arial;text-align:center;padding:50px;background:#667eea;color:#fff">
<h1>🎵</h1><p style="font-size:2em">
{'🎉 تشغيل فعلي!' if (userbot_available and pytgcalls_available) else '⚠️ معلومات فقط'}
</p><p>Bot: @{bot_username or 'Loading'}</p>
<p>UserBot: {'✅' if userbot_available else '❌'}</p>
<p>PyTgCalls: {'✅' if pytgcalls_available else '❌'}</p>
</body></html>"""
    return web.Response(text=html, content_type='text/html')

async def start_web():
    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_get('/health', health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()
    logger.info(f"✅ Web on {PORT}")

# ========================= Main =========================
async def main():
    global bot_username

    logger.info("🎵 MUSIC BOT")

    await bot.start()
    me = await bot.get_me()
    bot_username = me.username
    logger.info(f"✅ Bot: @{me.username}")

    if userbot_available:
        await userbot.start()
        logger.info(f"✅ UserBot: {(await userbot.get_me()).first_name}")

        if pytgcalls_available:
            await calls.start()
            logger.info("✅ pytgcalls: STARTED")
            logger.info("🎉 FULL PLAYBACK READY!")

    await start_web()
    logger.info("✅ READY!")

    await asyncio.Event().wait()

if __name__ == "__main__":
    bot.run(main())
