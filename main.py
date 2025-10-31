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
PORT = int(os.getenv("PORT", 8080))  # Choreo/Cloud Run عادة 8080
ASSISTANT_USERNAME = os.getenv("ASSISTANT_USERNAME")  # اختياري: لعرضه في رسائل الإرشاد

# مسار تخزين الوسائط المؤقتة (لملفات تيليجرام)
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

# ========================= Compat Patch (fix GroupcallForbidden import) =========================
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

# ========================= FFmpeg Ensurer (Choreo/Cloud friendly) =========================
FFMPEG_URL_DEFAULT = os.getenv(
    "FFMPEG_STATIC_URL",
    "https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz"
)

def _first_writable_exec_dir(candidates):
    for d in candidates:
        try:
            os.makedirs(d, exist_ok=True)
            test_file = os.path.join(d, ".perm_test")
            with open(test_file, "w") as f:
                f.write("ok")
            os.chmod(test_file, 0o755)
            os.remove(test_file)
            return d
        except Exception:
            continue
    return None

async def ensure_ffmpeg():
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    if ffmpeg_path and ffprobe_path:
        logger.info(f"✅ ffmpeg found at {ffmpeg_path}, ffprobe found at {ffprobe_path}")
        return

    candidate_dirs = [
        "/workspace/ffbin",
        "/home/runner/bin",
        "/home/site/bin",
        "/opt/bin",
        "/tmp/ffbin",
    ]
    ffbin_dir = _first_writable_exec_dir(candidate_dirs)
    if not ffbin_dir:
        logger.warning("⚠️ No writable exec dir found; ffmpeg install skipped.")
        return

    if platform.system().lower() != "linux":
        logger.warning("⚠️ Non-Linux platform detected. Please install ffmpeg/ffprobe manually.")
        return

    url = FFMPEG_URL_DEFAULT
    logger.info(f"⬇️ Downloading static FFmpeg from: {url}")

    tmp_dir = tempfile.mkdtemp(prefix="ffmpegdl_")
    archive_path = os.path.join(tmp_dir, "ffmpeg.tar.xz")
    extract_dir = os.path.join(tmp_dir, "extract")
    os.makedirs(extract_dir, exist_ok=True)

    import aiohttp
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(url, timeout=90) as resp:
                resp.raise_for_status()
                with open(archive_path, "wb") as f:
                    while True:
                        chunk = await resp.content.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
    except Exception as e:
        logger.error(f"❌ Failed to download FFmpeg: {e}")
        return

    try:
        with tarfile.open(archive_path, "r:xz") as tar:
            tar.extractall(extract_dir)
    except Exception as e:
        logger.error(f"❌ Failed to extract FFmpeg archive: {e}")
        return

    found_ffmpeg = None
    found_ffprobe = None

    for root, dirs, files in os.walk(extract_dir):
        if "ffmpeg" in files:
            src = os.path.join(root, "ffmpeg")
            dst = os.path.join(ffbin_dir, "ffmpeg")
            shutil.copy2(src, dst)
            os.chmod(dst, 0o755)
            found_ffmpeg = dst
        if "ffprobe" in files:
            src = os.path.join(root, "ffprobe")
            dst = os.path.join(ffbin_dir, "ffprobe")
            shutil.copy2(src, dst)
            os.chmod(dst, 0o755)
            found_ffprobe = dst

    if not (found_ffmpeg and found_ffprobe):
        logger.error("❌ Failed to locate ffmpeg/ffprobe in extracted archive.")
        return

    os.environ["PATH"] = f"{ffbin_dir}:{os.environ.get('PATH', '')}"
    logger.info(f"✅ FFmpeg ready at {shutil.which('ffmpeg')}, FFprobe at {shutil.which('ffprobe')}")

# ========================= PyTgCalls setup (version-agnostic) =========================
pytgcalls_available = False
calls = None
HAVE_MEDIA_STREAM = False

if userbot_available:
    try:
        from pytgcalls import PyTgCalls
        calls = PyTgCalls(userbot)
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
playback_timers: Dict[int, asyncio.Task] = {}

# ========================= YouTube cookies support =========================
COOKIES_FILE_CACHED = None

async def prepare_youtube_cookies() -> str | None:
    global COOKIES_FILE_CACHED
    if COOKIES_FILE_CACHED:
        return COOKIES_FILE_CACHED
    txt = None
    b64 = os.getenv("YT_COOKIES_B64")
    raw = os.getenv("YT_COOKIES")
    url = os.getenv("YT_COOKIES_URL")
    try:
        if b64:
            txt = base64.b64decode(b64).decode("utf-8", "ignore")
        elif raw:
            txt = raw
        elif url:
            import aiohttp
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url, timeout=20) as r:
                    r.raise_for_status()
                    txt = await r.text()
        if txt:
            path = "/tmp/yt_cookies.txt"
            with open(path, "w", encoding="utf-8") as f:
                f.write(txt)
            COOKIES_FILE_CACHED = path
            logger.info("✅ YouTube cookies prepared")
            return path
    except Exception as e:
        logger.warning(f"⚠️ Failed to prepare cookies: {e}")
    return None

# ========================= YouTube ydl_opts =========================
ydl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'geo_bypass': True,
    'ignoreerrors': True,
    'extractor_args': {
        'youtube': {
            'player_client': ['android'],
            'skip': ['hls_manifest_time_shift']
        }
    },
    'retries': 5,
    'fragment_retries': 5,
}

async def download_song(query: str):
    try:
        logger.info(f"🔍 Searching: {query}")
        stats['songs_searched'] += 1
        local_opts = dict(ydl_opts)
        cookies_path = await prepare_youtube_cookies()
        if cookies_path:
            local_opts['cookiefile'] = cookies_path
            local_opts['nocheckcertificate'] = True

        def extract():
            with yt_dlp.YoutubeDL(local_opts) as ydl:
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
            'id': info.get('id', ''),
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

# ========================= Helpers (UI) =========================
def human_time(seconds: float) -> str:
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    parts = []
    if days: parts.append(f"{days}d")
    if hours: parts.append(f"{hours}h")
    if mins: parts.append(f"{mins}m")
    parts.append(f"{secs}s")
    return " ".join(parts)

def main_menu_kb() -> InlineKeyboardMarkup:
    rows = []
    if bot_username:
        rows.append([InlineKeyboardButton("➕ أضِفني إلى مجموعة", url=f"https://t.me/{bot_username}?startgroup=true")])
    rows.append([
        InlineKeyboardButton("📚 المساعدة", callback_data="help"),
        InlineKeyboardButton("📋 القائمة", callback_data="queue")
    ])
    return InlineKeyboardMarkup(rows)

def build_player_keyboard(paused: bool = False, source_url: str | None = None) -> InlineKeyboardMarkup:
    row1 = [
        InlineKeyboardButton("▶️" if paused else "⏸️", callback_data="resume" if paused else "pause"),
        InlineKeyboardButton("⏭️", callback_data="skip"),
        InlineKeyboardButton("⏹️", callback_data="stop"),
    ]
    row2 = [InlineKeyboardButton("📋 القائمة", callback_data="queue")]
    if source_url:
        row2.append(InlineKeyboardButton("🔗 المصدر", url=source_url))
    return InlineKeyboardMarkup([row1, row2])

def build_queue_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏭️ تخطي", callback_data="skip"),
            InlineKeyboardButton("⏹️ إيقاف", callback_data="stop"),
        ]
    ])

# ========================= Helpers =========================
async def resolve_target_chat_id(chat):
    if getattr(chat, "type", None) == "channel":
        return chat.id
    linked = getattr(chat, "linked_chat", None)
    if linked:
        try:
            return linked.id
        except:
            pass
    return chat.id

async def ensure_userbot_peer(chat_id: int) -> bool:
    try:
        await userbot.get_chat(chat_id)
        return True
    except PeerIdInvalid:
        return False
    except Exception as e:
        logger.warning(f"ensure_userbot_peer: {e}")
        return False

async def join_chat(chat_id: int, invoker: Message = None) -> bool:
    if not userbot_available:
        return False
    try:
        try:
            await userbot.get_chat_member(chat_id, "me")
            return True
        except (UserNotParticipant, PeerIdInvalid):
            pass

        chat = None
        try:
            chat = await bot.get_chat(chat_id)
        except Exception as e:
            logger.warning(f"get_chat by bot failed: {e}")

        if chat and getattr(chat, "username", None):
            try:
                await userbot.join_chat(chat.username)
                await asyncio.sleep(0.5)
                await userbot.get_chat_member(chat_id, "me")
                logger.info(f"✅ UserBot joined via @{chat.username}")
                return True
            except Exception as e:
                logger.warning(f"join via username failed: {e}")

        # محاولة رابط دعوة
        try:
            invite_link = await bot.export_chat_invite_link(chat_id)
            try:
                await userbot.join_chat(invite_link)
                await asyncio.sleep(0.5)
                await userbot.get_chat_member(chat_id, "me")
                logger.info("✅ UserBot joined via invite link")
                return True
            except Exception as e:
                logger.warning(f"join via invite failed: {e}")
        except ChatAdminRequired:
            logger.warning("⚠️ Bot is not admin to export invite link")
        except Exception as e:
            logger.warning(f"export_chat_invite_link failed: {e}")

        helper = None
        try:
            helper = ASSISTANT_USERNAME or (await userbot.get_me()).username or "assistant_account"
        except Exception:
            helper = ASSISTANT_USERNAME or "assistant_account"

        # لا ترسل إلى الدردشة الهدف (قد لا يكون البوت عضواً)، بل رد على المنفذ إن توفر
        if invoker:
            await invoker.reply_text(
                f"❌ تعذّر إضافة الحساب المساعد تلقائياً.\n\n"
                f"الرجاء إضافة الحساب المساعد يدوياً ثم أعد المحاولة:\n"
                f"• الحساب المساعد: @{helper}\n\n"
                f"أو أرسل رابط دعوة واستخدم: `/forcejoin <invite-link>`\n"
                f"وتأكد من وجود محادثة صوتية نشطة قبل التشغيل."
            )
        else:
            logger.warning("Assistant join failed and no invoker to notify.")
        return False

    except UserAlreadyParticipant:
        return True
    except Exception as e:
        logger.error(f"Join error: {e}")
        if invoker:
            await invoker.reply_text(f"❌ فشل الانضمام: {e}")
        return False

def cancel_timer(chat_id: int):
    t = playback_timers.pop(chat_id, None)
    if t and not t.done():
        t.cancel()

def set_timer(chat_id: int, task: asyncio.Task):
    cancel_timer(chat_id)
    playback_timers[chat_id] = task

def create_playback_timer(chat_id: int, song_id: str, sleep_sec: float) -> asyncio.Task:
    async def runner():
        try:
            await asyncio.sleep(max(1, sleep_sec))
            cur = currently_playing.get(chat_id)
            if cur and cur.get('id') == song_id:
                await play_next_song(chat_id)
        except asyncio.CancelledError:
            pass
        finally:
            cur_t = playback_timers.get(chat_id)
            if cur_t is asyncio.current_task():
                playback_timers.pop(chat_id, None)
    return asyncio.create_task(runner())

# ========================= PyTgCalls Safe Wrappers =========================
async def safe_play(chat_id: int, url: str):
    if HAVE_MEDIA_STREAM and hasattr(globals().get('MediaStream', object), '__call__'):
        return await calls.play(chat_id, MediaStream(url, audio_parameters=AudioQuality.HIGH))  # type: ignore
    return await calls.play(chat_id, url)

async def safe_change_stream(chat_id: int, url: str):
    if hasattr(calls, 'change_stream'):
        if HAVE_MEDIA_STREAM and hasattr(globals().get('MediaStream', object), '__call__'):
            return await calls.change_stream(chat_id, MediaStream(url, audio_parameters=AudioQuality.HIGH))  # type: ignore
        return await calls.change_stream(chat_id, url)
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

# ========================= Utils for input =========================
def extract_url_from_message(msg) -> str | None:
    if not msg:
        return None
    text = None
    if getattr(msg, "text", None):
        text = msg.text
    elif getattr(msg, "caption", None):
        text = msg.caption
    if text:
        m = re.search(r'(https?://\S+)', text)
        if m:
            return m.group(1).rstrip(').,]}>')
    return None

def guess_ext_from_mime(mime: str | None) -> str:
    if not mime:
        return "ogg"
    mime = mime.lower()
    if "mpeg" in mime or "mp3" in mime:
        return "mp3"
    if "ogg" in mime or "opus" in mime:
        return "ogg"
    if "mp4" in mime or "m4a" in mime or "aac" in mime:
        return "m4a"
    if "wav" in mime:
        return "wav"
    return "ogg"

def build_local_file_url(filename: str) -> str:
    return f"http://127.0.0.1:{PORT}/files/{filename}"

# ========================= Telegram media enqueue =========================
async def enqueue_tg_media(invoker_msg: Message, media_msg: Message):
    chat_id = await resolve_target_chat_id(invoker_msg.chat)

    tg_audio = media_msg.audio
    tg_voice = media_msg.voice

    if not tg_audio and not tg_voice:
        return await invoker_msg.reply_text("❌ الرسالة لا تحتوي على ملف صوتي/رسالة صوتية")

    if tg_audio:
        duration = int(tg_audio.duration or 0)
        title = tg_audio.title or tg_audio.file_name or "Telegram Audio"
        performer = getattr(tg_audio, "performer", None)
        uploader = performer or (invoker_msg.from_user.first_name if invoker_msg.from_user else "Telegram")
        ext = os.path.splitext(tg_audio.file_name or "")[1].lstrip(".") or guess_ext_from_mime(tg_audio.mime_type)
        file_unique_id = tg_audio.file_unique_id
    else:
        duration = int(tg_voice.duration or 0)
        title = "Voice message"
        uploader = invoker_msg.from_user.first_name if invoker_msg.from_user else "Telegram"
        ext = "ogg"
        file_unique_id = tg_voice.file_unique_id

    filename = f"{int(time.time())}_{invoker_msg.id}_{file_unique_id}.{ext}"
    target_path = os.path.join(TMP_MEDIA_DIR, filename)

    try:
        await media_msg.download(file_name=target_path)
    except Exception as e:
        logger.error(f"Download tg media error: {e}")
        return await invoker_msg.reply_text("❌ فشل تنزيل الملف من تيليجرام")

    url = build_local_file_url(filename)

    song_info = {
        'id': file_unique_id,
        'title': title,
        'url': url,
        'duration': duration,
        'thumbnail': '',
        'webpage_url': '',
        'uploader': uploader,
        'view_count': 0,
        'like_count': 0
    }

    if chat_id not in music_queue:
        music_queue[chat_id] = []
    music_queue[chat_id].append(song_info)
    position = len(music_queue[chat_id])

    if pytgcalls_available and (chat_id not in currently_playing):
        if not await join_chat(chat_id, invoker=invoker_msg):
            return
        ok = await play_next_song(chat_id)
        if not ok:
            return await invoker_msg.reply_text("❌ فشل التشغيل. تأكد من وجود محادثة صوتية نشطة.")
        return await invoker_msg.reply_text(
            f"▶️ بدأ التشغيل الآن:\n\n"
            f"🎵 {song_info['title']}\n"
            f"👤 {song_info['uploader']}\n"
            f"⏱️ {format_duration(duration)}"
        )
    else:
        return await invoker_msg.reply_text(
            f"✅ تمت الإضافة إلى القائمة #{position}\n\n"
            f"🎵 {song_info['title']}\n"
            f"👤 {song_info['uploader']}\n"
            f"⏱️ {format_duration(duration)}",
            reply_markup=build_queue_keyboard()
        )

# ========================= Core Playback =========================
async def play_next_song(chat_id: int):
    if not pytgcalls_available or not calls:
        return False

    if chat_id not in music_queue or not music_queue[chat_id]:
        try:
            cancel_timer(chat_id)
            await safe_leave(chat_id)
            if chat_id in currently_playing:
                del currently_playing[chat_id]
            try:
                await bot.send_message(chat_id, "📭 انتهت قائمة التشغيل")
            except Exception:
                pass
        except Exception:
            pass
        return False

    if userbot_available and not await ensure_userbot_peer(chat_id):
        # لا ترسل في الدردشة لأن البوت قد لا يراها
        return False

    next_song = music_queue[chat_id].pop(0)

    try:
        cancel_timer(chat_id)
        await safe_play(chat_id, next_song['url'])

        next_song['_started_at'] = time.time()
        next_song['_paused_at'] = None
        currently_playing[chat_id] = next_song
        stats['songs_played'] += 1
        logger.info(f"▶️ Playing: {next_song['title']}")

        dur = int(next_song.get('duration') or 0)
        if dur > 0:
            task = create_playback_timer(chat_id, next_song.get('id', ''), dur + 2)
            set_timer(chat_id, task)

        keyboard = build_player_keyboard(
            paused=False,
            source_url=(next_song.get('webpage_url') or None)
        )

        try:
            await bot.send_message(
                chat_id,
                f"▶️ يتم التشغيل الآن\n"
                f"🎵 {next_song['title']}\n"
                f"👤 {next_song.get('uploader') or 'Unknown'}\n"
                f"⏱️ {format_duration(dur)}",
                reply_markup=keyboard
            )
        except Exception:
            pass
        return True

    except Exception as e:
        msg = str(e).lower()
        logger.error(f"❌ Play error: {msg}")

        if "no active group call" in msg or "group_call_invalid" in msg or "groupcall" in msg:
            try:
                await bot.send_message(chat_id, "❌ لا توجد محادثة صوتية نشطة! ابدأ مكالمة صوتية ثم أعد المحاولة.")
            except Exception:
                pass
            return False

        if "already" in msg or "joined" in msg or "in call" in msg or "already joined" in msg:
            try:
                await safe_change_stream(chat_id, next_song['url'])
                next_song['_started_at'] = time.time()
                next_song['_paused_at'] = None
                currently_playing[chat_id] = next_song
                stats['songs_played'] += 1
                dur = int(next_song.get('duration') or 0)
                if dur > 0:
                    task = create_playback_timer(chat_id, next_song.get('id', ''), dur + 2)
                    set_timer(chat_id, task)
                try:
                    await bot.send_message(
                        chat_id,
                        f"▶️ تم التبديل إلى:\n🎵 {next_song['title']}",
                        reply_markup=build_player_keyboard(False, next_song.get('webpage_url') or None)
                    )
                except Exception:
                    pass
                return True
            except Exception as e2:
                logger.error(f"❌ Change stream error: {e2}")
                return await play_next_song(chat_id)

        return await play_next_song(chat_id)

# ========================= Commands =========================
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message: Message):
    stats['messages'] += 1
    stats['users'].add(message.from_user.id)
    await message.reply_text(
        f"🎵 أهلاً {message.from_user.mention}!\n\n"
        f"أنا بوت لتشغيل الموسيقى في المجموعات والقنوات عبر المكالمات الصوتية.\n\n"
        f"الحالة الحالية:\n"
        f"• التشغيل الفعلي: {'✅ متاح' if (userbot_available and pytgcalls_available) else '⚠️ معلومات فقط'}\n\n"
        f"للبدء:\n"
        f"1) أضفني كمشرف في مجموعتك/قناتك\n"
        f"2) ابدأ محادثة صوتية\n"
        f"3) استخدم: /play اسم_أغنية أو ارفع ملفاً صوتياً مباشرة\n"
        f"{'4) إن لزم: أضف الحساب المساعد @' + ASSISTANT_USERNAME if ASSISTANT_USERNAME else ''}",
        reply_markup=main_menu_kb()
    )

@bot.on_message(filters.command("help"))
async def help_cmd(client, message: Message):
    stats['messages'] += 1
    await message.reply_text(
        "📚 الأوامر المتاحة:\n\n"
        "• /play [أغنية|رابط] — تشغيل/إضافة للقائمة\n"
        "• /play (بدون اسم) — استئناف أو تشغيل أول عنصر بالقائمة أو تشغيل ردّك على رابط/ملف\n"
        "• ارفع ملف Audio/Voice — يُضاف مباشرةً ويُشغّل عند الإمكان\n\n"
        "التحكم أثناء التشغيل:\n"
        "• /pause — إيقاف مؤقت\n"
        "• /resume — استئناف\n"
        "• /skip — تخطي الحالي\n"
        "• /stop — إيقاف كامل وإخلاء القائمة\n"
        "• /queue — عرض القائمة الحالية\n\n"
        "أخرى:\n"
        "• /ping — فحص الحالة\n"
        "• /forcejoin <invite-link> — ضمّ الحساب المساعد عبر رابط دعوة",
        reply_markup=main_menu_kb()
    )

@bot.on_message(filters.command("ping"))
async def ping_cmd(client, message: Message):
    stats['messages'] += 1
    start = time.time()
    msg = await message.reply_text("🏓 جاري القياس...")
    end = time.time()
    uptime = human_time(time.time() - stats['start_time'])
    await msg.edit(
        "🏓 Pong!\n\n"
        f"⚡ سرعة الاستجابة: {round((end-start)*1000, 2)}ms\n"
        f"⏱️ وقت التشغيل: {uptime}\n"
        f"🤖 Bot: ✅\n"
        f"👤 UserBot: {'✅' if userbot_available else '❌'}\n"
        f"🎵 PyTgCalls: {'✅' if pytgcalls_available else '❌'}\n"
        f"▶️ حالياً: {len(currently_playing)} تشغيل"
    )

@bot.on_message(filters.command("forcejoin"))
async def forcejoin_cmd(client, message: Message):
    if not userbot_available:
        return await message.reply_text("❌ لا يوجد حساب مساعد مفعّل (SESSION_STRING).")
    link = None
    if len(message.command) >= 2:
        link = message.command[1]
    elif message.reply_to_message:
        link = extract_url_from_message(message.reply_to_message)
    if not link:
        return await message.reply_text("ℹ️ الاستخدام: /forcejoin <invite-link> أو رد على رسالة تحوي رابط الدعوة.")
    try:
        await userbot.join_chat(link)
        await asyncio.sleep(0.5)
        target_id = await resolve_target_chat_id(message.chat)
        try:
            await userbot.get_chat_member(target_id, "me")
            return await message.reply_text("✅ تم انضمام الحساب المساعد بنجاح لهذه الدردشة.")
        except Exception:
            return await message.reply_text("ℹ️ تم الانضمام عبر الرابط. إن استمرت المشكلة، أعد /play بعد بدء المكالمة.")
    except Exception as e:
        return await message.reply_text(f"❌ فشل الانضمام عبر الرابط: {e}")

# /play مع دعم بدون اسم والرد على رابط/ملف
@bot.on_message(filters.command(["play", "p"]) & (filters.group | filters.channel))
async def play_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    stats['groups'].add(message.chat.id)

    chat_id = await resolve_target_chat_id(message.chat)

    if not userbot_available or not pytgcalls_available:
        if len(message.command) < 2:
            return await message.reply_text(
                "❌ التشغيل الفعلي غير متاح حالياً.\n\n"
                "يمكنك استخدام /play بدون اسم كما يلي:\n"
                "• استئناف التشغيل إن كان متوقفاً\n"
                "• تشغيل أول عنصر في قائمة الانتظار\n"
                "• الرد على رابط YouTube أو ملف صوتي ثم إرسال /play"
            )
        return await message.reply_text("❌ التشغيل الفعلي غير متاح حالياً.")

    # === /play بدون اسم ===
    if len(message.command) < 2:
        cur = currently_playing.get(chat_id)
        if cur and cur.get('_paused_at'):
            try:
                await safe_resume(chat_id)
                dur = int(cur.get('duration') or 0)
                started = cur.get('_started_at') or time.time()
                paused_at = cur.get('_paused_at')
                if dur > 0:
                    elapsed = max(0, (paused_at or time.time()) - started)
                    remain = max(3, dur - int(elapsed))
                    cur['_started_at'] = time.time() - elapsed
                    cur['_paused_at'] = None
                    task = create_playback_timer(chat_id, cur.get('id', ''), remain + 1)
                    set_timer(chat_id, task)
                return await message.reply_text("▶️ تم الاستئناف")
            except Exception as e:
                logger.error(f"Resume error: {e}")

        if chat_id in music_queue and music_queue[chat_id]:
            await message.reply_text("▶️ تشغيل أول عنصر من قائمة الانتظار...")
            ok = await play_next_song(chat_id)
            if not ok:
                return await message.reply_text("❌ حدثت مشكلة في التشغيل. تأكد من وجود محادثة صوتية نشطة.")
            return

        if message.reply_to_message:
            if message.reply_to_message.audio or message.reply_to_message.voice:
                return await enqueue_tg_media(message, message.reply_to_message)
            link = extract_url_from_message(message.reply_to_message)
            if link:
                msg = await message.reply_text("🔄 جارِ التحضير (بدون اسم)...")
                if not await join_chat(chat_id, invoker=message):
                    return
                await msg.edit("🔍 جارِ تحليل الرابط...")
                song_info = await download_song(link)
                if not song_info:
                    return await msg.edit("❌ لم أتمكن من تحليل الرابط! قد يتطلب YouTube تمرير Cookies.")
                if chat_id not in music_queue:
                    music_queue[chat_id] = []
                music_queue[chat_id].append(song_info)
                if chat_id not in currently_playing:
                    await msg.edit("🎵 بدء التشغيل...")
                    ok = await play_next_song(chat_id)
                    if not ok:
                        return await msg.edit("❌ فشل التشغيل. تأكد من وجود محادثة صوتية نشطة.")
                else:
                    return await msg.edit(
                        f"✅ تمت الإضافة للقائمة #{len(music_queue[chat_id])}\n\n"
                        f"🎵 {song_info['title']}\n"
                        f"⏱️ {format_duration(int(song_info.get('duration') or 0))}",
                    )
                return

        link = extract_url_from_message(message)
        if link:
            msg = await message.reply_text("🔄 جارِ التحضير (بدون اسم)...")
            if not await join_chat(chat_id, invoker=message):
                return
            await msg.edit("🔍 جارِ تحليل الرابط...")
            song_info = await download_song(link)
            if not song_info:
                return await msg.edit("❌ لم أتمكن من تحليل الرابط! قد يتطلب YouTube تمرير Cookies.")
            if chat_id not in music_queue:
                music_queue[chat_id] = []
            music_queue[chat_id].append(song_info)
            if chat_id not in currently_playing:
                await msg.edit("🎵 بدء التشغيل...")
                ok = await play_next_song(chat_id)
                if not ok:
                    return await msg.edit("❌ فشل التشغيل. تأكد من وجود محادثة صوتية نشطة.")
            else:
                return await msg.edit(
                    f"✅ تمت الإضافة للقائمة #{len(music_queue[chat_id])}\n\n"
                    f"🎵 {song_info['title']}\n"
                    f"⏱️ {format_duration(int(song_info.get('duration') or 0))}",
                )
            return

        return await message.reply_text(
            "ℹ️ استخدام /play بدون اسم:\n"
            "• إن كان التشغيل متوقفاً مؤقتاً: سيتم الاستئناف\n"
            "• إن كانت هناك قائمة انتظار: سيبدأ تشغيل أول عنصر\n"
            "• أو قم بالرد على رابط/ملف صوتي ثم أرسل /play"
        )

    # ====== الحالة الأصلية مع اسم/بحث ======
    query = " ".join(message.command[1:])
    msg = await message.reply_text("🔄 جارِ التحضير...")

    if not await join_chat(chat_id, invoker=message):
        return

    await msg.edit("🔍 جارِ البحث...")
    song_info = await download_song(query)
    if not song_info:
        return await msg.edit("❌ لم أجد نتيجة مناسبة!")

    if chat_id not in music_queue:
        music_queue[chat_id] = []

    music_queue[chat_id].append(song_info)
    position = len(music_queue[chat_id])

    if chat_id not in currently_playing:
        await msg.edit("🎵 بدء التشغيل...")
        if not await play_next_song(chat_id):
            return await msg.delete()
    else:
        await msg.edit(
            f"✅ تمت الإضافة للقائمة #{position}\n\n"
            f"🎵 {song_info['title']}\n"
            f"⏱️ {format_duration(int(song_info.get('duration') or 0))}",
        )

@bot.on_message((filters.audio | filters.voice) & (filters.group | filters.channel))
async def tg_audio_handler(client, message: Message):
    stats['messages'] += 1
    if not userbot_available or not pytgcalls_available:
        return await message.reply_text("❌ التشغيل الفعلي غير متاح حالياً")
    await enqueue_tg_media(message, message)

@bot.on_message(filters.command("pause") & (filters.group | filters.channel))
async def pause_cmd(client, message: Message):
    stats['messages'] += 1
    if not pytgcalls_available:
        return
    try:
        cancel_timer(message.chat.id)
        cur = currently_playing.get(message.chat.id)
        if cur and not cur.get('_paused_at'):
            cur['_paused_at'] = time.time()
        await safe_pause(message.chat.id)
        await message.reply_text("⏸️ تم الإيقاف المؤقت")
    except Exception as e:
        await message.reply_text(f"❌ {e}")

@bot.on_message(filters.command("resume") & (filters.group | filters.channel))
async def resume_cmd(client, message: Message):
    stats['messages'] += 1
    if not pytgcalls_available:
        return
    try:
        await safe_resume(message.chat.id)
        cur = currently_playing.get(message.chat.id)
        if cur:
            dur = int(cur.get('duration') or 0)
            started = cur.get('_started_at') or time.time()
            paused_at = cur.get('_paused_at')
            if dur > 0:
                elapsed = 0
                if paused_at:
                    elapsed = max(0, paused_at - started)
                else:
                    elapsed = max(0, time.time() - started)
                remain = max(3, dur - int(elapsed))
                cur['_started_at'] = time.time() - elapsed
                cur['_paused_at'] = None
                task = create_playback_timer(message.chat.id, cur.get('id', ''), remain + 1)
                set_timer(message.chat.id, task)
        await message.reply_text("▶️ تم الاستئناف")
    except Exception as e:
        await message.reply_text(f"❌ {e}")

@bot.on_message(filters.command("skip") & (filters.group | filters.channel))
async def skip_cmd(client, message: Message):
    stats['messages'] += 1
    chat_id = message.chat.id
    if chat_id not in currently_playing:
        return await message.reply_text("❌ لا يوجد شيء لتخطيه")
    cancel_timer(chat_id)
    await message.reply_text(f"⏭️ تم التخطي: {currently_playing[chat_id]['title']}")
    await play_next_song(chat_id)

@bot.on_message(filters.command("stop") & (filters.group | filters.channel))
async def stop_cmd(client, message: Message):
    stats['messages'] += 1
    chat_id = message.chat.id
    try:
        cancel_timer(chat_id)
        if pytgcalls_available:
            await safe_leave(chat_id)
        if chat_id in music_queue:
            music_queue[chat_id] = []
        if chat_id in currently_playing:
            del currently_playing[chat_id]
        await message.reply_text("⏹️ تم الإيقاف وإفراغ القائمة")
    except Exception as e:
        await message.reply_text(f"❌ {e}")

@bot.on_message(filters.command("queue") & (filters.group | filters.channel))
async def queue_cmd(client, message: Message):
    stats['messages'] += 1
    chat_id = message.chat.id
    text = ""

    if chat_id in currently_playing:
        cur = currently_playing[chat_id]
        text += "🎶 الآن قيد التشغيل:\n"
        text += f"• {cur['title']} — {format_duration(int(cur.get('duration') or 0))}\n\n"

    if chat_id in music_queue and music_queue[chat_id]:
        text += "📋 قائمة الانتظار:\n"
        for i, s in enumerate(music_queue[chat_id][:10], 1):
            text += f"{i}. {s['title']} — {format_duration(int(s.get('duration') or 0))}\n"

    await message.reply_text(text or "📭 القائمة فارغة", reply_markup=build_queue_keyboard())

# ========================= Callback =========================
@bot.on_callback_query()
async def callback_handler(client, query: CallbackQuery):
    data = query.data
    # ملاحظة: نستخدم الأوامر نفسها لتوحيد السلوك
    try:
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
    finally:
        try:
            await query.answer()
        except Exception:
            pass

# ========================= Web Server =========================
async def health(request):
    return web.Response(text="OK")

async def index(request):
    html = f"""
<html>
  <body style="font-family:Arial,Helvetica,sans-serif;text-align:center;padding:60px;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff">
    <div style="max-width:720px;margin:auto">
      <h1 style="font-size:64px;margin:0">🎵</h1>
      <h2 style="font-weight:700;margin:10px 0 30px">{'🎉 التشغيل الفعلي جاهز!' if (userbot_available and pytgcalls_available) else '⚠️ وضع المعلومات فقط'}</h2>
      <p style="font-size:18px;line-height:1.6">
        Bot: @{bot_username or 'Loading...'}<br/>
        UserBot: {'✅' if userbot_available else '❌'} · PyTgCalls: {'✅' if pytgcalls_available else '❌'}<br/>
        منفذ الويب: {PORT}
      </p>
      <p style="opacity:.9">أضف البوت إلى مجموعتك وشغّل محادثة صوتية ثم استخدم /play</p>
    </div>
  </body>
</html>
"""
    return web.Response(text=html, content_type='text/html')

async def start_web():
    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_get('/health', health)
    app.router.add_static('/files', TMP_MEDIA_DIR, show_index=False)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()
    logger.info(f"✅ Web on {PORT}")

# ========================= Main =========================
async def main():
    global bot_username

    logger.info("🎵 MUSIC BOT")

    await ensure_ffmpeg()  # تأكد من ffmpeg/ffprobe

    await bot.start()
    me = await bot.get_me()
    bot_username = me.username
    logger.info(f"✅ Bot: @{me.username}")

    if userbot_available:
        await userbot.start()
        try:
            me2 = await userbot.get_me()
            logger.info(f"✅ UserBot: {me2.first_name}")
        except Exception as e:
            logger.warning(f"[userbot] get_me: {e}")

        if pytgcalls_available:
            await calls.start()
            logger.info("✅ pytgcalls: STARTED")
            logger.info("🎉 FULL PLAYBACK READY!")

    await start_web()
    logger.info("✅ READY!")

    await asyncio.Event().wait()

if __name__ == "__main__":
    bot.run(main())
