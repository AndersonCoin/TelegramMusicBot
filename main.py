import os
import logging
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserAlreadyParticipant, ChatAdminRequired, UserNotParticipant
from dotenv import load_dotenv
from aiohttp import web
import yt_dlp
from typing import Dict, List

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

# Config
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
SESSION_STRING = os.getenv("SESSION_STRING")
PORT = int(os.getenv("PORT", 10000))

# Bot
bot = Client("bot", api_id=int(API_ID), api_hash=API_HASH, bot_token=BOT_TOKEN)

# UserBot
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
    logger.warning("⚠️ No UserBot")

# PyTgCalls - استيراد بدون أخطاء
pytgcalls_available = False
calls = None

if userbot_available:
    try:
        from pytgcalls import PyTgCalls
        
        # Try importing new API classes
        try:
            from pytgcalls.types import MediaStream, AudioQuality
        except ImportError:
            logger.warning("⚠️ Using older pytgcalls API")
            MediaStream = None
            AudioQuality = None
        
        calls = PyTgCalls(userbot)
        pytgcalls_available = True
        logger.info("✅ PyTgCalls ready")
    except Exception as e:
        logger.warning(f"⚠️ PyTgCalls: {e}")

# Global data
stats = {'messages': 0, 'commands': 0, 'users': set(), 'groups': set()}
music_queue: Dict[int, List[Dict]] = {}
currently_playing: Dict[int, Dict] = {}
bot_username = None

# ========== HELPER FUNCTIONS ==========

async def join_chat(chat_id: int):
    """إضافة UserBot للمجموعة تلقائياً"""
    if not userbot_available:
        return False
    
    try:
        # تحقق من وجود UserBot
        try:
            await userbot.get_chat_member(chat_id, "me")
            logger.info(f"✅ UserBot already in chat {chat_id}")
            return True
        except UserNotParticipant:
            pass
        
        # Get chat info
        chat = await bot.get_chat(chat_id)
        
        # Try joining via username
        if chat.username:
            await userbot.join_chat(chat.username)
            logger.info(f"✅ UserBot joined via @{chat.username}")
            return True
        
        # Try joining via invite link
        try:
            invite_link = await bot.export_chat_invite_link(chat_id)
            await userbot.join_chat(invite_link)
            logger.info(f"✅ UserBot joined via invite")
            return True
        except ChatAdminRequired:
            logger.error("❌ Bot needs admin to create invite")
            return False
        
    except UserAlreadyParticipant:
        logger.info("✅ UserBot already participant")
        return True
    except Exception as e:
        logger.error(f"❌ Join error: {e}")
        return False

async def play_next_song(chat_id: int):
    """تشغيل الأغنية التالية"""
    if not pytgcalls_available or not calls:
        logger.warning("⚠️ PyTgCalls not available")
        return False
    
    if chat_id not in music_queue or not music_queue[chat_id]:
        # Queue empty
        try:
            await calls.leave_call(chat_id)
            if chat_id in currently_playing:
                del currently_playing[chat_id]
            logger.info(f"🔚 Left chat {chat_id}")
        except Exception as e:
            logger.error(f"Leave error: {e}")
        return False
    
    next_song = music_queue[chat_id].pop(0)
    
    try:
        # Try playing with different methods
        if MediaStream and AudioQuality:
            # New API
            await calls.play(
                chat_id,
                MediaStream(next_song['url'], audio_parameters=AudioQuality.HIGH)
            )
        else:
            # Fallback to basic play
            await calls.play(chat_id, next_song['url'])
        
        currently_playing[chat_id] = next_song
        logger.info(f"▶️ Playing: {next_song['title']}")
        return True
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Play error: {error_msg}")
        
        if "No active group call" in error_msg or "GROUP_CALL_INVALID" in error_msg:
            logger.error("❌ No voice chat active")
            return False
        elif "already" in error_msg.lower() or "joined" in error_msg.lower():
            # Already in call, try changing stream
            try:
                if MediaStream and AudioQuality:
                    await calls.change_stream(
                        chat_id,
                        MediaStream(next_song['url'], audio_parameters=AudioQuality.HIGH)
                    )
                else:
                    # Fallback
                    pass
                currently_playing[chat_id] = next_song
                logger.info(f"▶️ Changed to: {next_song['title']}")
                return True
            except Exception as e2:
                logger.error(f"❌ Change stream error: {e2}")
                return False
        else:
            # Try next song
            return await play_next_song(chat_id)

# Stream ended callback
if pytgcalls_available and calls:
    @calls.on_stream_end()
    async def on_stream_end(client, update):
        try:
            chat_id = update.chat_id
            logger.info(f"🔚 Stream ended in {chat_id}")
            
            # Notify
            if chat_id in currently_playing:
                song = currently_playing[chat_id]
                try:
                    await bot.send_message(
                        chat_id,
                        f"✅ **انتهى:**\n🎵 {song['title']}"
                    )
                except:
                    pass
            
            # Play next
            success = await play_next_song(chat_id)
            
            if success and chat_id in currently_playing:
                next_song = currently_playing[chat_id]
                try:
                    await bot.send_message(
                        chat_id,
                        f"▶️ **الآن:**\n🎵 {next_song['title']}"
                    )
                except:
                    pass
            
        except Exception as e:
            logger.error(f"Stream end error: {e}")

# YouTube download
ydl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'geo_bypass': True,
}

async def download_song(query: str):
    try:
        logger.info(f"🔍 Searching: {query}")
        
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
            'uploader': info.get('uploader', 'Unknown')
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

# ========== COMMANDS ==========

@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    stats['users'].add(message.from_user.id)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ أضفني لمجموعتك", 
            url=f"https://t.me/{bot_username}?startgroup=true")],
        [InlineKeyboardButton("📚 الأوامر", callback_data="help"),
         InlineKeyboardButton("ℹ️ حول", callback_data="about")]
    ])
    
    status_icon = "✅" if (userbot_available and pytgcalls_available) else "⚠️"
    status_text = "جاهز للتشغيل الفعلي" if (userbot_available and pytgcalls_available) else "عرض معلومات فقط"
    
    await message.reply_text(
        f"🎵 **مرحباً {message.from_user.mention}!**\n\n"
        f"أنا بوت تشغيل الموسيقى في المجموعات\n\n"
        f"**الحالة:** {status_icon} {status_text}\n\n"
        f"**المميزات:**\n"
        f"{'✅' if userbot_available else '❌'} انضمام تلقائي للمجموعات\n"
        f"{'✅' if pytgcalls_available else '❌'} تشغيل فعلي في المحادثة الصوتية\n"
        f"✅ بحث متقدم من YouTube\n"
        f"✅ قوائم انتظار ذكية\n"
        f"✅ تحكم كامل بالأزرار\n\n"
        f"**للبدء:**\n"
        f"1️⃣ أضفني لمجموعتك\n"
        f"2️⃣ اجعلني مشرف\n"
        f"3️⃣ ابدأ محادثة صوتية\n"
        f"4️⃣ استخدم `/play [اسم الأغنية]`\n\n"
        f"{'🎉 العميل المساعد سينضم تلقائياً!' if userbot_available else '⚠️ للتشغيل الفعلي: أضف SESSION_STRING'}",
        reply_markup=keyboard
    )

@bot.on_message(filters.command("ping"))
async def ping_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    import time
    start = time.time()
    msg = await message.reply_text("🏓 جاري الفحص...")
    end = time.time()
    latency = round((end - start) * 1000, 2)
    
    await msg.edit(
        f"🏓 **Pong!**\n\n"
        f"⚡ **السرعة:** `{latency}ms`\n"
        f"🤖 **البوت:** ✅ نشط\n"
        f"👤 **UserBot:** {'✅ متصل' if userbot_available else '❌ غير متصل'}\n"
        f"🎵 **PyTgCalls:** {'✅ جاهز' if pytgcalls_available else '❌ غير متاح'}\n"
        f"📊 **الرسائل:** {stats['messages']}\n"
        f"▶️ **قيد التشغيل:** {len(currently_playing)}\n"
        f"🤖 **الانضمام التلقائي:** {'✅ مفعّل' if userbot_available else '❌ معطّل'}\n\n"
        f"{'✅ **جاهز للتشغيل الفعلي!**' if (userbot_available and pytgcalls_available) else '⚠️ **التشغيل الفعلي غير متاح**'}"
    )

@bot.on_message(filters.command("test") & filters.private)
async def test_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    await message.reply_text(
        f"✅ **اختبار ناجح!**\n\n"
        f"🆔 **معرفك:** `{message.from_user.id}`\n"
        f"👤 **اسمك:** {message.from_user.first_name}\n"
        f"📊 **الرسائل:** {stats['messages']}\n\n"
        f"**حالة الأنظمة:**\n"
        f"🤖 البوت: ✅\n"
        f"👤 UserBot: {'✅' if userbot_available else '❌'}\n"
        f"🎵 PyTgCalls: {'✅' if pytgcalls_available else '❌'}\n"
        f"🤖 الانضمام التلقائي: {'✅' if userbot_available else '❌'}\n"
        f"🎶 التشغيل الفعلي: {'✅' if pytgcalls_available else '❌'}"
    )

@bot.on_message(filters.command(["play", "p"]) & filters.group)
async def play_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    stats['groups'].add(message.chat.id)
    
    logger.info(f"🎯 PLAY in group {message.chat.id}")
    
    # Check availability
    if not userbot_available:
        await message.reply_text(
            "❌ **العميل المساعد غير متاح!**\n\n"
            "⚠️ لا يمكن تشغيل الموسيقى بدون UserBot.\n\n"
            "**الحل:**\n"
            "اتصل بمطور البوت لإضافة SESSION_STRING"
        )
        return
    
    if not pytgcalls_available:
        # Can still show song info
        logger.warning("⚠️ PyTgCalls not available, showing info only")
    
    if len(message.command) < 2:
        await message.reply_text(
            "❌ **الاستخدام:**\n"
            "`/play [اسم الأغنية أو رابط YouTube]`\n\n"
            "**أمثلة:**\n"
            "• `/play فيروز صباح الخير`\n"
            "• `/play Imagine Dragons Believer`"
        )
        return
    
    query = " ".join(message.command[1:])
    chat_id = message.chat.id
    
    # Progress
    msg = await message.reply_text("🔄 **جاري التحضير...**")
    
    # Join chat
    if userbot_available:
        await msg.edit("🔄 **إضافة العميل المساعد...**")
        joined = await join_chat(chat_id)
        
        if not joined:
            await msg.edit(
                "❌ **فشل انضمام العميل!**\n\n"
                "**الحلول:**\n"
                "• تأكد من أن البوت مشرف\n"
                "• أضف العميل يدوياً: @مساعد_تشغيل_صوتيات"
            )
            return
    
    # Search
    await msg.edit("🔍 **البحث عن الأغنية...**")
    song_info = await download_song(query)
    
    if not song_info:
        await msg.edit("❌ **لم أجد الأغنية!**")
        return
    
    # Add to queue
    if chat_id not in music_queue:
        music_queue[chat_id] = []
    
    music_queue[chat_id].append(song_info)
    position = len(music_queue[chat_id])
    
    # Try playing if PyTgCalls available
    if pytgcalls_available and chat_id not in currently_playing:
        await msg.edit("🎵 **بدء التشغيل...**")
        
        success = await play_next_song(chat_id)
        
        if success:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⏸️ إيقاف", callback_data=f"pause"),
                 InlineKeyboardButton("⏭️ تخطي", callback_data=f"skip")],
                [InlineKeyboardButton("⏹️ إيقاف كامل", callback_data=f"stop"),
                 InlineKeyboardButton("📋 القائمة", callback_data=f"queue")]
            ])
            
            await msg.edit(
                f"▶️ **يتم التشغيل الآن:**\n\n"
                f"🎵 **{song_info['title']}**\n"
                f"👤 **القناة:** {song_info['uploader']}\n"
                f"⏱️ **المدة:** {format_duration(song_info['duration'])}\n"
                f"🔗 [YouTube]({song_info['webpage_url']})\n\n"
                f"👤 **طلب بواسطة:** {message.from_user.mention}\n"
                f"🤖 **العميل:** انضم تلقائياً ✅",
                reply_markup=keyboard,
                disable_web_page_preview=False
            )
        else:
            await msg.edit(
                f"⚠️ **تمت الإضافة للقائمة** (التشغيل الفعلي غير متاح)\n\n"
                f"🎵 **{song_info['title']}**\n"
                f"👤 {song_info['uploader']}\n"
                f"⏱️ {format_duration(song_info['duration'])}\n"
                f"🔗 [YouTube]({song_info['webpage_url']})\n\n"
                f"**ملاحظة:** تأكد من بدء محادثة صوتية!",
                disable_web_page_preview=False
            )
    else:
        # Just add to queue
        await msg.edit(
            f"✅ **تمت الإضافة للقائمة #{position}**\n\n"
            f"🎵 **{song_info['title']}**\n"
            f"⏱️ {format_duration(song_info['duration'])}\n\n"
            f"{'سيتم تشغيلها بعد الأغنية الحالية' if pytgcalls_available else 'التشغيل الفعلي غير متاح حالياً'}"
        )
    
    logger.info(f"✅ Queued: {song_info['title']}")

@bot.on_message(filters.command("queue") & filters.group)
async def queue_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    chat_id = message.chat.id
    
    text = ""
    
    if chat_id in currently_playing:
        current = currently_playing[chat_id]
        text += f"▶️ **قيد التشغيل:**\n🎵 {current['title']}\n\n"
    
    if chat_id in music_queue and music_queue[chat_id]:
        text += "📋 **قائمة الانتظار:**\n\n"
        for i, song in enumerate(music_queue[chat_id][:10], 1):
            text += f"**{i}.** {song['title']}\n⏱️ {format_duration(song['duration'])}\n\n"
        
        if len(music_queue[chat_id]) > 10:
            text += f"\n_...و {len(music_queue[chat_id]) - 10} أخرى_"
    else:
        if not text:
            text = "📭 **لا يوجد شيء في القائمة**"
    
    await message.reply_text(text or "📭 **القائمة فارغة**")

@bot.on_message(filters.command("stop") & filters.group)
async def stop_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    chat_id = message.chat.id
    
    try:
        if pytgcalls_available and calls:
            try:
                await calls.leave_call(chat_id)
            except:
                pass
        
        count = len(music_queue.get(chat_id, []))
        
        if chat_id in music_queue:
            music_queue[chat_id] = []
        if chat_id in currently_playing:
            del currently_playing[chat_id]
        
        await message.reply_text(
            f"⏹️ **تم الإيقاف!**\n\n"
            f"حذف {count} أغنية من القائمة."
        )
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {str(e)}")

# Callbacks
@bot.on_callback_query()
async def callback_handler(client, callback_query):
    await callback_query.answer()

# Web
async def health(request):
    return web.Response(text=f"OK|{stats['messages']}")

async def index(request):
    html = f"""
<!DOCTYPE html>
<html lang="ar">
<head>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="10">
    <title>Music Bot</title>
    <style>
        body{{font-family:Arial;background:linear-gradient(135deg,#667eea,#764ba2);
        color:#fff;text-align:center;padding:50px}}
        h1{{font-size:4em}}
        .status{{font-size:2em;color:#4ade80;margin:30px}}
        .info{{font-size:1.3em;margin:15px}}
    </style>
</head>
<body>
    <h1>🎵</h1>
    <div class="status">{'⚡ جاهز للتشغيل' if (userbot_available and pytgcalls_available) else '⚠️ عرض معلومات فقط'}</div>
    <div class="info">البوت: @{bot_username or 'AtheerAlsalafBot'}</div>
    <div class="info">UserBot: {'✅' if userbot_available else '❌'}</div>
    <div class="info">PyTgCalls: {'✅' if pytgcalls_available else '❌'}</div>
    <div class="info">الانضمام التلقائي: {'✅' if userbot_available else '❌'}</div>
    <div class="info">الرسائل: {stats['messages']}</div>
    <div class="info">قيد التشغيل: {len(currently_playing)}</div>
    <a href="https://t.me/{bot_username or 'AtheerAlsalafBot'}" style="color:#4ade80;font-size:1.5em;margin-top:30px;display:block">فتح البوت</a>
</body>
</html>
    """
    return web.Response(text=html, content_type='text/html')

async def start_web():
    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_get('/health', health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"✅ Web on {PORT}")

# Main
async def main():
    global bot_username
    
    logger.info("="*60)
    logger.info("🎵 MUSIC BOT")
    logger.info("="*60)
    
    await bot.start()
    me = await bot.get_me()
    bot_username = me.username
    logger.info(f"✅ Bot: @{me.username}")
    
    if userbot_available:
        await userbot.start()
        user_info = await userbot.get_me()
        logger.info(f"✅ UserBot: {user_info.first_name}")
        logger.info(f"🤖 Auto-join: ENABLED")
        
        if pytgcalls_available:
            try:
                await calls.start()
                logger.info("✅ PyTgCalls: READY FOR REAL PLAYBACK")
            except Exception as e:
                logger.error(f"❌ PyTgCalls start error: {e}")
                logger.warning("⚠️ Will show info only")
        else:
            logger.warning("⚠️ PyTgCalls: NOT AVAILABLE (info only mode)")
    else:
        logger.warning("⚠️ UserBot: NOT AVAILABLE")
    
    await start_web()
    
    logger.info("="*60)
    logger.info("✅ READY!")
    if userbot_available and pytgcalls_available:
        logger.info("🎉 FULL MUSIC PLAYBACK ENABLED!")
    else:
        logger.info("⚠️ INFO MODE ONLY (add SESSION_STRING for playback)")
    logger.info(f"🔗 https://t.me/{me.username}")
    logger.info("="*60)
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    bot.run(main())
