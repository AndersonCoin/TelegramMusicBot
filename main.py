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

# ✨✨✨  إضافة جديدة: متغيرات زر القناة ✨✨✨
CHANNEL_NAME = os.getenv("CHANNEL_NAME", "Channel")
CHANNEL_URL = os.getenv("CHANNEL_URL")


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

# ... (باقي الكود من `Compat Patch` إلى `enqueue_tg_media` يبقى كما هو) ...
# سأقوم بلصق الكود الكامل من بعد هذا الجزء لضمان عدم تفويت أي شيء

# ========================= Compat Patch, FFmpeg, PyTgCalls setup, State, YouTube helpers, etc. =========================
# (هذا الجزء لم يتغير، لذا سأفترض وجوده هنا لتجنب تكرار الكود الطويل)
# ...
# ... (افترض أن كل الأكواد المساعدة من الإجابة السابقة موجودة هنا) ...
# ...


# ========================= Core Playback & UI =========================

# ✨✨✨  الجزء المعدل: دالة إنشاء الأزرار الجديدة بأسلوب الصورة  ✨✨✨
def generate_image_style_keyboard(is_paused: bool, song_info: dict) -> InlineKeyboardMarkup:
    """Creates a keyboard layout inspired by the user's provided image."""
    
    # تحديد زر التشغيل/الإيقاف المؤقت
    play_pause_icon = "▶️" if is_paused else "⏸️"
    play_pause_callback = "resume" if is_paused else "pause"

    keyboard = [
        # الصف الأول: التحكمات الأساسية
        [
            InlineKeyboardButton("⏮", callback_data="previous"),
            InlineKeyboardButton(play_pause_icon, callback_data=play_pause_callback),
            InlineKeyboardButton("⏭️", callback_data="skip"),
            InlineKeyboardButton("⏹️", callback_data="stop"),
        ],
    ]

    # الصف الثاني: زر القناة (إذا تم توفير الرابط)
    if CHANNEL_URL and CHANNEL_NAME:
        keyboard.append([
            InlineKeyboardButton(f"⟫ {CHANNEL_NAME} ⟪", url=CHANNEL_URL)
        ])
    
    # الصف الثالث: زر الإغلاق
    keyboard.append([
        InlineKeyboardButton("乂", callback_data="close_menu")
    ])

    return InlineKeyboardMarkup(keyboard)


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
                await bot.send_message(chat_id, "📭 انتهت قائمة الانتظار. سأغادر المحادثة الصوتية.")
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

        # ✨✨✨  التعديل: استخدام الدالة الجديدة لإنشاء الأزرار بالأسلوب المطلوب  ✨✨✨
        keyboard = generate_image_style_keyboard(is_paused=False, song_info=next_song)
        
        # تصميم الرسالة لمحاكاة الشكل في الصورة
        requested_by = "Unknown" # Placeholder, this needs to be passed down
        
        message_text = (
            f"**YT sτяєαмiиg ♪**\n\n"
            f"▸ **ᴛɪᴛʟᴇ :** {next_song.get('title', 'Unknown Title')}\n"
            f"▸ **ᴅᴜʀᴀᴛɪᴏɴ :** {format_duration(dur)}\n"
            #f"▸ **ʀᴇǫᴜᴇsᴛᴇᴅ ʙʏ :** {requested_by}" # You'd need to track who requested the song for this
        )

        try:
            # إرسال صورة ثابتة مع الرسالة والأزرار
            await bot.send_photo(
                chat_id,
                photo="https://telegra.ph/file/b9289a878562d2a23354c.jpg", # رابط صورة مضرب التنس
                caption=message_text,
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Failed to send 'now playing' message with photo: {e}")
            # Fallback to text message if photo fails
            await bot.send_message(chat_id, message_text, reply_markup=keyboard, disable_web_page_preview=True)

        return True

    except Exception as e:
        # ... (باقي معالجة الأخطاء تبقى كما هي)
        msg = str(e).lower()
        logger.error(f"❌ Play error: {msg}")
        if "no active group call" in msg:
            try:
                await bot.send_message(chat_id, "❌ **لا توجد محادثة صوتية نشطة!**")
            except Exception: pass
        return False # Simplified error handling for brevity

# ... (جميع أوامر البوت مثل /start, /help, /ping, /play تبقى كما هي) ...

# ✨✨✨  الجزء المعدل: تحديث معالج الأزرار التفاعلية (CallbackQuery)  ✨✨✨
@bot.on_callback_query(filters.regex("^(pause|resume|skip|stop|queue|previous|close_menu)$"))
async def playback_controls_cq(client, query: CallbackQuery):
    chat_id = query.message.chat.id
    data = query.data

    if data == "close_menu":
        try:
            await query.message.delete()
        except:
            pass
        return await query.answer("Menu closed.")

    if not userbot_available or not pytgcalls_available:
        return await query.answer("❌ التشغيل غير متاح حالياً.", show_alert=True)

    currently_playing_song = currently_playing.get(chat_id)
    if not currently_playing_song:
        await query.message.delete()
        return await query.answer("❌ التشغيل قد توقف بالفعل.", show_alert=True)

    if data == "pause":
        await safe_pause(chat_id)
        currently_playing_song['_paused_at'] = time.time()
        cancel_timer(chat_id)
        keyboard = generate_image_style_keyboard(is_paused=True, song_info=currently_playing_song)
        await query.message.edit_reply_markup(keyboard)
        await query.answer("⏸️ تم الإيقاف المؤقت")

    elif data == "resume":
        await safe_resume(chat_id)
        # ... (نفس منطق الاستئناف من الإجابة السابقة) ...
        paused_at = currently_playing_song.get('_paused_at', time.time())
        pause_duration = time.time() - paused_at
        if '_started_at' in currently_playing_song:
            currently_playing_song['_started_at'] += pause_duration
        currently_playing_song['_paused_at'] = None
        dur = int(currently_playing_song.get('duration', 0))
        elapsed = time.time() - currently_playing_song.get('_started_at', time.time())
        if dur > 0 and (remaining := dur - elapsed) > 0:
            set_timer(chat_id, create_playback_timer(chat_id, currently_playing_song.get('id', ''), remaining + 2))
        
        keyboard = generate_image_style_keyboard(is_paused=False, song_info=currently_playing_song)
        await query.message.edit_reply_markup(keyboard)
        await query.answer("▶️ تم الاستئناف")

    elif data == "skip":
        await query.answer("⏭️ جاري التخطي...")
        await play_next_song(chat_id)
        await query.message.delete()

    elif data == "stop":
        await query.answer("⏹️ جاري الإيقاف...")
        music_queue[chat_id] = []
        await play_next_song(chat_id) # This will trigger the leave logic
        await query.message.delete()
        
    elif data == "previous":
        #  منطق زر "السابق" يمكن أن يكون معقداً. حالياً سيعرض رسالة.
        await query.answer("⏮️ ميزة 'الأغنية السابقة' قيد التطوير!", show_alert=True)
        
    elif data == "queue":
        await query.answer()
        await queue_cmd(client, query.message, from_callback=True)

# ... (باقي الكود مثل /queue والأوامر الأخرى و run_web_server يبقى كما هو) ...

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
    await web_task


if __name__ == "__main__":
    try:
        # Note: You need to keep the other functions (like play_cmd, queue_cmd, etc.) from the previous answer
        # for the bot to be fully functional. I have only shown the modified parts here.
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Bot shutting down...")
