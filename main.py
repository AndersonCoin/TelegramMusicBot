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
import random
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
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "RosaliaChannel")

# قيود التحكم (اختياري): اجعل التحكم بالمشرفين فقط
ENFORCE_ADMIN = os.getenv("ENFORCE_ADMIN", "false").lower() == "true"
CALLBACK_COOLDOWN = float(os.getenv("CALLBACK_COOLDOWN", "0.8"))  # ثواني تبريد لكل مستخدم

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

# ========================= Compat Patch =========================
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

# ========================= FFmpeg Ensurer =========================
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

# ========================= State =========================
stats = {
    'messages': 0, 
    'commands': 0, 
    'users': set(), 
    'groups': set(),
    'songs_searched': 0, 
    'songs_played': 0, 
    'start_time': time.time(),
    'button_presses': 0,
    'button_details': {}
}
music_queue: Dict[int, List[Dict]] = {}
currently_playing: Dict[int, Dict] = {}
bot_username = None
playback_timers: Dict[int, asyncio.Task] = {}
_last_cb_ts: Dict[tuple, float] = {}  # (chat_id, user_id) -> last_ts

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
        logger.error(f"Download error: {e}", exc_info=True)
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
        InlineKeyboardButton("📋 القائمة", callback_data="showqueue")  # fix: showqueue موحّد
    ])
    return InlineKeyboardMarkup(rows)

def build_advanced_player_keyboard(chat_id: int, is_paused: bool = False) -> InlineKeyboardMarkup:
    """
    3 صفوف:
    1) ▶️/⏸️ | ⏭️ | ⏹️
    2) ⏪ -10 | ⏱️ elapsed/total | ⏩ +10
    3) 🔔 القناة | 📋 القائمة | ❌ حذف | 🔀 خلط
    """
    cur = currently_playing.get(chat_id)
    if cur:
        if cur.get('_paused_at'):
            # عند الإيقاف المؤقت نظهر الوقت حين التوقف
            elapsed = int(cur['_paused_at'] - cur.get('_started_at', time.time()))
        else:
            elapsed = int(time.time() - cur.get('_started_at', time.time()))
        duration = int(cur.get('duration', 0))
        current_time_display = f"⏱️ {format_duration(elapsed)}/{format_duration(duration)}"
    else:
        current_time_display = "⏱️ --:--/--:--"

    row1 = [
        InlineKeyboardButton("▶️ تشغيل" if is_paused else "⏸️ إيقاف", callback_data=f"playpause_{chat_id}"),
        InlineKeyboardButton("⏭️ التالي", callback_data=f"skip_{chat_id}"),
        InlineKeyboardButton("⏹️ إيقاف", callback_data=f"stop_{chat_id}")
    ]
    row2 = [
        InlineKeyboardButton("⏪ -10", callback_data=f"seekback_{chat_id}"),
        InlineKeyboardButton(current_time_display, callback_data=f"noop_{chat_id}"),
        InlineKeyboardButton("⏩ +10", callback_data=f"seekfwd_{chat_id}")
    ]
    row3 = []
    if CHANNEL_USERNAME:
        row3.append(InlineKeyboardButton("🔔 القناة", url=f"https://t.me/{CHANNEL_USERNAME}"))
    row3.extend([
        InlineKeyboardButton("📋 القائمة", callback_data=f"showqueue_{chat_id}"),
        InlineKeyboardButton("❌ حذف", callback_data=f"delete_{chat_id}"),
        InlineKeyboardButton("🔀 خلط", callback_data=f"shuffle_{chat_id}")
    ])
    return InlineKeyboardMarkup([row1, row2, row3])

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

        if invoker:
            await invoker.reply_text(
                f"❌ تعذّر إضافة الحساب المساعد تلقائياً.\n\n"
                f"الرجاء إضافة الحساب المساعد يدوياً: @{helper}\n"
                f"أو استخدم: `/forcejoin <invite-link>`"
            )
        else:
            logger.warning("Assistant join failed and no invoker to notify.")
        return False

    except UserAlreadyParticipant:
        return True
    except Exception as e:
        logger.error(f"Join error: {e}", exc_info=True)
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
    if HAVE_MEDIA_STREAM:
        return await calls.play(chat_id, MediaStream(url, audio_parameters=AudioQuality.HIGH))
    return await calls.play(chat_id, url)

async def safe_change_stream(chat_id: int, url: str):
    if hasattr(calls, 'change_stream'):
        if HAVE_MEDIA_STREAM:
            return await calls.change_stream(chat_id, MediaStream(url, audio_parameters=AudioQuality.HIGH))
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

# ========================= Cleanup old files =========================
async def cleanup_old_media_files():
    try:
        current_time = time.time()
        count = 0
        for filename in os.listdir(TMP_MEDIA_DIR):
            filepath = os.path.join(TMP_MEDIA_DIR, filename)
            if os.path.isfile(filepath):
                file_age = current_time - os.path.getmtime(filepath)
                if file_age > 3600:
                    os.remove(filepath)
                    count += 1
        if count > 0:
            logger.info(f"🗑️ Cleaned up {count} old media file(s)")
    except Exception as e:
        logger.warning(f"Cleanup error: {e}")

async def periodic_cleanup():
    while True:
        await asyncio.sleep(1800)
        await cleanup_old_media_files()

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
        file_size = tg_audio.file_size
    else:
        duration = int(tg_voice.duration or 0)
        title = "Voice message"
        uploader = invoker_msg.from_user.first_name if invoker_msg.from_user else "Telegram"
        ext = "ogg"
        file_unique_id = tg_voice.file_unique_id
        file_size = tg_voice.file_size

    filename = f"{int(time.time())}_{invoker_msg.id}_{file_unique_id}.{ext}"
    target_path = os.path.join(TMP_MEDIA_DIR, filename)

    # تنزيل مع إعادة محاولة وتحقق
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"📥 Downloading TG media (attempt {attempt}/{max_retries}): {filename}")
            await media_msg.download(file_name=target_path)
            
            if not os.path.exists(target_path):
                raise Exception("File not found after download")
            actual_size = os.path.getsize(target_path)
            if actual_size == 0:
                raise Exception("Downloaded file is empty (0 bytes)")
            if file_size and actual_size < (file_size * 0.8):
                raise Exception(f"File incomplete: expected ~{file_size} bytes, got {actual_size} bytes")
            logger.info(f"✅ Downloaded successfully: {filename} ({actual_size} bytes)")
            break
        except Exception as e:
            logger.error(
                f"❌ Download attempt {attempt}/{max_retries} failed for {filename}: {e}",
                exc_info=(attempt == max_retries)
            )
            if os.path.exists(target_path):
                try:
                    os.remove(target_path)
                except:
                    pass
            if attempt == max_retries:
                return await invoker_msg.reply_text(
                    f"❌ فشل تنزيل الملف من تيليجرام بعد {max_retries} محاولات.\n"
                    f"السبب: {str(e)}\n\n"
                    f"💡 جرّب مرة أخرى بعد قليل."
                )
            await asyncio.sleep(2)

    url = build_local_file_url(filename)

    song_info = {
        'id': file_unique_id,
        'title': title,
        'url': url,
        'local_path': target_path,  # حفظ المسار المحلي للاستخدام المستقبلي
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
        return
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
        return False

    next_song = music_queue[chat_id].pop(0)

    try:
        cancel_timer(chat_id)
        # مبدئياً نستمر باستخدام URL؛ المسار المحلي محفوظ إن رغبت لاحقاً باستبدال FFmpeg للملف المحلي
        source = next_song.get('url')

        await safe_play(chat_id, source)

        next_song['_started_at'] = time.time()
        next_song['_paused_at'] = None
        currently_playing[chat_id] = next_song
        stats['songs_played'] += 1
        logger.info(f"▶️ Playing: {next_song['title']} in chat {chat_id}")

        dur = int(next_song.get('duration') or 0)
        if dur > 0:
            task = create_playback_timer(chat_id, next_song.get('id', ''), dur + 2)
            set_timer(chat_id, task)

        keyboard = build_advanced_player_keyboard(chat_id, is_paused=False)

        try:
            caption = (
                f"▶️ **يتم التشغيل الآن**\n"
                f"🎵 **{next_song['title']}**\n"
                f"👤 {next_song.get('uploader') or 'Unknown'}\n"
                f"⏱️ {format_duration(dur)}"
            )
            if next_song.get('thumbnail'):
                await bot.send_photo(
                    chat_id,
                    photo=next_song['thumbnail'],
                    caption=caption,
                    reply_markup=keyboard
                )
            else:
                await bot.send_message(
                    chat_id,
                    caption,
                    reply_markup=keyboard
                )
        except Exception as send_e:
            logger.error(f"Failed to send now playing message: {send_e}")
        
        return True

    except Exception as e:
        msg = str(e).lower() if e else "unknown error"
        logger.error(
            f"❌ Play error in chat {chat_id}: {msg}",
            exc_info=True
        )

        if "no active group call" in msg or "group_call_invalid" in msg or "groupcall" in msg:
            try:
                await bot.send_message(chat_id, "❌ لا توجد محادثة صوتية نشطة!")
            except Exception:
                pass
            return False

        if "already" in msg or "joined" in msg or "in call" in msg:
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
                        reply_markup=build_advanced_player_keyboard(chat_id, False)
                    )
                except Exception:
                    pass
                return True
            except Exception as e2:
                logger.error(f"❌ Change stream error in chat {chat_id}: {e2}", exc_info=True)
                return await play_next_song(chat_id)

        return await play_next_song(chat_id)

# ========================= Commands =========================
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message: Message):
    stats['messages'] += 1
    stats['users'].add(message.from_user.id)
    await message.reply_text(
        f"🎵 أهلاً {message.from_user.mention}!\n\n"
        f"أنا بوت موسيقى متقدم للمجموعات والقنوات.\n\n"
        f"الحالة: {'✅ جاهز للتشغيل' if (userbot_available and pytgcalls_available) else '⚠️ معلومات فقط'}\n\n"
        f"للبدء:\n"
        f"1) أضفني كمشرف\n"
        f"2) ابدأ محادثة صوتية\n"
        f"3) استخدم: /play [اسم الأغنية]",
        reply_markup=main_menu_kb()
    )

@bot.on_message(filters.command("help"))
async def help_cmd(client, message: Message):
    stats['messages'] += 1
    await message.reply_text(
        "📚 **الأوامر المتاحة:**\n\n"
        "• `/play [أغنية]` — تشغيل/إضافة\n"
        "• `/skip` — تخطي الحالي\n"
        "• `/stop` — إيقاف كامل\n"
        "• `/queue` — عرض القائمة\n"
        "• `/shuffle` — خلط القائمة\n"
        "• `/ping` — فحص الحالة\n\n"
        "💡 يمكنك التحكم بالتشغيل عبر الأزرار التفاعلية!",
        reply_markup=main_menu_kb()
    )

@bot.on_message(filters.command("ping"))
async def ping_cmd(client, message: Message):
    stats['messages'] += 1
    start = time.time()
    msg = await message.reply_text("🏓 جاري القياس...")
    end = time.time()
    uptime = human_time(time.time() - stats['start_time'])
    most_used_button = "لا يوجد"
    if stats['button_details']:
        most_used_button = max(stats['button_details'], key=stats['button_details'].get)
    await msg.edit(
        f"🏓 Pong!\n\n"
        f"⚡ {round((end-start)*1000, 2)}ms\n"
        f"⏱️ وقت التشغيل: {uptime}\n"
        f"🤖 Bot: ✅\n"
        f"👤 UserBot: {'✅' if userbot_available else '❌'}\n"
        f"🎵 PyTgCalls: {'✅' if pytgcalls_available else '❌'}\n"
        f"▶️ نشط في: {len(currently_playing)} محادثة\n"
        f"🎼 إجمالي التشغيل: {stats['songs_played']}\n"
        f"🔘 ضغطات الأزرار: {stats['button_presses']}\n"
        f"🏆 الأكثر استخداماً: {most_used_button}"
    )

@bot.on_message(filters.command("shuffle"))
async def shuffle_cmd(client, message: Message):
    stats['messages'] += 1
    chat_id = message.chat.id
    if chat_id not in music_queue or not music_queue[chat_id]:
        return await message.reply_text("📭 القائمة فارغة!")
    random.shuffle(music_queue[chat_id])
    await message.reply_text(f"🔀 تم خلط القائمة ({len(music_queue[chat_id])} أغنية)")

@bot.on_message(filters.command("forcejoin"))
async def forcejoin_cmd(client, message: Message):
    if not userbot_available:
        return await message.reply_text("❌ لا يوجد حساب مساعد.")
    link = None
    if len(message.command) >= 2:
        link = message.command[1]
    elif message.reply_to_message:
        link = extract_url_from_message(message.reply_to_message)
    if not link:
        return await message.reply_text("ℹ️ الاستخدام: /forcejoin <invite-link>")
    try:
        await userbot.join_chat(link)
        await asyncio.sleep(0.5)
        return await message.reply_text("✅ تم الانضمام بنجاح.")
    except Exception as e:
        logger.error(f"Forcejoin error: {e}", exc_info=True)
        return await message.reply_text(f"❌ فشل: {e}")

@bot.on_message(filters.command(["play", "p"]) & (filters.group | filters.channel))
async def play_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    stats['groups'].add(message.chat.id)

    chat_id = await resolve_target_chat_id(message.chat)

    if not userbot_available or not pytgcalls_available:
        return await message.reply_text("❌ التشغيل غير متاح حالياً.")

    if len(message.command) < 2:
        return await message.reply_text("🤔 ماذا تريد أن أُشغل؟")

    query = " ".join(message.command[1:])
    msg = await message.reply_text("🔄 جارِ البحث...")

    if not await join_chat(chat_id, invoker=message):
        return

    song_info = await download_song(query)
    if not song_info:
        return await msg.edit("❌ لم أجد الأغنية!")

    if chat_id not in music_queue:
        music_queue[chat_id] = []

    music_queue[chat_id].append(song_info)

    if chat_id not in currently_playing:
        await msg.delete()
        await play_next_song(chat_id)
    else:
        await msg.edit(
            f"✅ تمت الإضافة #{len(music_queue[chat_id])}\n"
            f"🎵 {song_info['title']}"
        )

@bot.on_message((filters.audio | filters.voice) & (filters.group | filters.channel))
async def tg_audio_handler(client, message: Message):
    stats['messages'] += 1
    if not userbot_available or not pytgcalls_available:
        return await message.reply_text("❌ **التشغيل غير متاح حالياً**")
    await enqueue_tg_media(message, message)

@bot.on_message(filters.command("skip") & (filters.group | filters.channel))
async def skip_cmd(client, message: Message):
    stats['messages'] += 1
    chat_id = message.chat.id
    if chat_id not in currently_playing:
        return await message.reply_text("❌ لا يوجد شيء لتخطيه")
    cancel_timer(chat_id)
    await message.reply_text(f"⏭️ تخطي: {currently_playing[chat_id]['title']}")
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
        await message.reply_text("⏹️ تم الإيقاف")
    except Exception as e:
        logger.error(f"Stop command error: {e}", exc_info=True)
        await message.reply_text(f"❌ {e}")

@bot.on_message(filters.command("queue") & (filters.group | filters.channel))
async def queue_cmd(client, message: Message):
    stats['messages'] += 1
    chat_id = message.chat.id
    text = ""

    if chat_id in currently_playing:
        cur = currently_playing[chat_id]
        text += f"🎶 الآن:\n• {cur['title']} — {format_duration(int(cur.get('duration') or 0))}\n\n"

    if chat_id in music_queue and music_queue[chat_id]:
        text += "📋 القائمة:\n"
        for i, s in enumerate(music_queue[chat_id][:10], 1):
            text += f"{i}. {s['title']} — {format_duration(int(s.get('duration') or 0))}\n"
        if len(music_queue[chat_id]) > 10:
            text += f"\n... و {len(music_queue[chat_id]) - 10} أغنية أخرى"

    await message.reply_text(text or "📭 القائمة فارغة")

# ========================= Callback Handler (UNIFIED & SMART) =========================
async def _can_control(chat_id: int, user_id: int) -> bool:
    if not ENFORCE_ADMIN:
        return True
    try:
        m = await bot.get_chat_member(chat_id, user_id)
        # مشرف/مالك أو المالك
        return getattr(m, "status", "") in ("administrator", "creator")
    except Exception:
        # إذا فشل الاستعلام، لا نمنع، لتجنّب تعطل التجربة
        return True

@bot.on_callback_query()
async def unified_callback_handler(client, query: CallbackQuery):
    # تبريد الضغطات لكل مستخدم
    key = (query.message.chat.id, query.from_user.id)
    now = time.time()
    if key in _last_cb_ts and (now - _last_cb_ts[key]) < CALLBACK_COOLDOWN:
        try:
            return await query.answer("⏳ لحظة من فضلك...", show_alert=False)
        finally:
            return
    _last_cb_ts[key] = now

    stats['button_presses'] += 1
    data = query.data
    start_time = time.time()

    try:
        parts = data.split("_", 1)
        command = parts[0]
        chat_id = int(parts[1]) if len(parts) > 1 else query.message.chat.id
    except:
        chat_id = query.message.chat.id
        command = data

    stats['button_details'][command] = stats['button_details'].get(command, 0) + 1
    logger.info(f"🔘 Button '{command}' by {query.from_user.id} in chat {chat_id}")

    try:
        # PLAY/PAUSE
        if command == "playpause":
            cur = currently_playing.get(chat_id)
            if not cur:
                return await query.answer("لا يوجد شيء قيد التشغيل.", show_alert=False)
            # لا نقيّد هذا الإجراء للمشرفين
            if cur.get('_paused_at'):
                await safe_resume(chat_id)
                paused_for = time.time() - cur['_paused_at']
                cur['_started_at'] += paused_for
                cur['_paused_at'] = None
                elapsed = time.time() - cur['_started_at']
                remaining = max(3, cur['duration'] - elapsed)
                set_timer(chat_id, create_playback_timer(chat_id, cur.get('id', ''), remaining + 1))
                await query.answer("▶️ تم الاستئناف")
                await query.edit_message_reply_markup(build_advanced_player_keyboard(chat_id, is_paused=False))
            else:
                await safe_pause(chat_id)
                cancel_timer(chat_id)
                cur['_paused_at'] = time.time()
                await query.answer("⏸️ تم الإيقاف المؤقت")
                await query.edit_message_reply_markup(build_advanced_player_keyboard(chat_id, is_paused=True))

        # SKIP
        elif command == "skip":
            if not await _can_control(chat_id, query.from_user.id):
                return await query.answer("🚫 هذا الإجراء للمشرفين فقط.", show_alert=True)
            if chat_id not in currently_playing:
                return await query.answer("لا يوجد شيء لتخطيه.", show_alert=False)
            await query.answer("⏭️ جارٍ التخطي...")
            cancel_timer(chat_id)
            try:
                await query.message.delete()
            except:
                pass
            await play_next_song(chat_id)

        # STOP
        elif command == "stop":
            if not await _can_control(chat_id, query.from_user.id):
                return await query.answer("🚫 هذا الإجراء للمشرفين فقط.", show_alert=True)
            cancel_timer(chat_id)
            await safe_leave(chat_id)
            title = currently_playing.get(chat_id, {}).get('title', '...')
            if chat_id in currently_playing:
                del currently_playing[chat_id]
            if chat_id in music_queue:
                music_queue[chat_id] = []
            await query.answer("⏹️ تم الإيقاف")
            try:
                await query.edit_message_caption(
                    caption=f"⏹️ **تم الإيقاف بواسطة {query.from_user.mention}**\n🎵 `{title}`",
                    reply_markup=None
                )
            except:
                await query.edit_message_text(
                    f"⏹️ **تم الإيقاف بواسطة {query.from_user.mention}**\n🎵 `{title}`",
                    reply_markup=None
                )

        # SEEK placeholders
        elif command in ["seekback", "seekfwd"]:
            await query.answer("⏩⏪ التقديم/التأخير غير مدعوم حالياً", show_alert=False)

        # NOOP
        elif command == "noop":
            await query.answer()

        # SHOW QUEUE (popup)
        elif command in ["showqueue", "show", "show_queue"]:
            text = ""
            if chat_id in currently_playing:
                cur = currently_playing[chat_id]
                text += f"🎶 الآن:\n• {cur['title']}\n\n"
            if chat_id in music_queue and music_queue[chat_id]:
                text += "📋 القائمة:\n"
                for i, s in enumerate(music_queue[chat_id][:10], 1):
                    text += f"{i}. {s['title']}\n"
                if len(music_queue[chat_id]) > 10:
                    text += f"\n... و {len(music_queue[chat_id]) - 10} أخرى"
            await query.answer(text or "📭 القائمة فارغة", show_alert=True)

        # DELETE message
        elif command == "delete":
            if not await _can_control(chat_id, query.from_user.id):
                return await query.answer("🚫 هذا الإجراء للمشرفين فقط.", show_alert=True)
            try:
                await query.message.delete()
            except:
                pass

        # SHUFFLE
        elif command == "shuffle":
            if not await _can_control(chat_id, query.from_user.id):
                return await query.answer("🚫 هذا الإجراء للمشرفين فقط.", show_alert=True)
            if chat_id not in music_queue or not music_queue[chat_id]:
                return await query.answer("📭 القائمة فارغة!", show_alert=False)
            random.shuffle(music_queue[chat_id])
            await query.answer(f"🔀 تم الخلط ({len(music_queue[chat_id])} أغنية)")

        # HELP
        elif command == "help":
            await query.message.reply_text(
                "📚 **الأوامر:**\n\n"
                "• `/play [أغنية]`\n"
                "• `/skip` — تخطي\n"
                "• `/stop` — إيقاف\n"
                "• `/queue` — القائمة\n"
                "• `/shuffle` — خلط",
                reply_markup=main_menu_kb()
            )
            await query.answer()

        else:
            await query.answer("أمر غير معروف", show_alert=False)

        elapsed = time.time() - start_time
        logger.info(f"✅ Callback '{command}' processed in {elapsed:.2f}s")

    except Exception as e:
        logger.error(
            f"❌ Callback error for '{data}' from user {query.from_user.id} in chat {chat_id}: {e}",
            exc_info=True
        )
        await query.answer(f"❌ خطأ: {e}", show_alert=True)
    finally:
        try:
            await query.answer()
        except:
            pass

# ========================= Web Server =========================
async def health(request):
    return web.Response(text="OK")

async def index(request):
    html = f"""
<html>
  <body style="font-family:Arial;text-align:center;padding:60px;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff">
    <div style="max-width:720px;margin:auto">
      <h1 style="font-size:64px;margin:0">🎵</h1>
      <h2 style="font-weight:700;margin:10px 0 30px">{'🎉 جاهز للتشغيل!' if (userbot_available and pytgcalls_available) else '⚠️ معلومات فقط'}</h2>
      <p style="font-size:18px">Bot: @{bot_username or 'Loading...'}<br/>UserBot: {'✅' if userbot_available else '❌'} · PyTgCalls: {'✅' if pytgcalls_available else '❌'}</p>
      <p>⏱️ Uptime: {human_time(time.time() - stats['start_time'])}</p>
      <p>🎼 Songs Played: {stats['songs_played']}</p>
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

    logger.info("🎵 ADVANCED MUSIC BOT - STARTING")

    await ensure_ffmpeg()

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
    asyncio.create_task(periodic_cleanup())
    logger.info("✅ ALL SYSTEMS READY!")

    await asyncio.Event().wait()

if __name__ == "__main__":
    bot.run(main())
