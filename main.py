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
    logger.warning("⚠️ No UserBot - Add SESSION_STRING to enable music playback")

# PyTgCalls - نسخة محدثة
pytgcalls_available = False
calls = None

if userbot_available:
    try:
        from pytgcalls import PyTgCalls
        from pytgcalls.types import AudioPiped, Update
        from pytgcalls.types.stream import StreamAudioEnded
        
        calls = PyTgCalls(userbot)
        pytgcalls_available = True
        logger.info("✅ PyTgCalls imported successfully")
    except ImportError as e:
        logger.error(f"❌ PyTgCalls import error: {e}")
        logger.error("Install: pip install git+https://github.com/pytgcalls/pytgcalls.git")
    except Exception as e:
        logger.error(f"❌ PyTgCalls error: {e}")

# Global data
stats = {'messages': 0, 'commands': 0, 'users': set(), 'groups': set()}
music_queue: Dict[int, List[Dict]] = {}
currently_playing: Dict[int, Dict] = {}
bot_username = None

# ========== HELPER FUNCTIONS ==========

async def join_chat(chat_id: int):
    """إضافة UserBot للمجموعة/القناة تلقائياً"""
    if not userbot_available:
        return False
    
    try:
        # Check if already member
        try:
            await userbot.get_chat_member(chat_id, "me")
            logger.info(f"✅ UserBot already in chat {chat_id}")
            return True
        except UserNotParticipant:
            pass
        
        # Get chat info
        chat = await bot.get_chat(chat_id)
        
        # Try joining via username (for public chats/channels)
        if chat.username:
            try:
                await userbot.join_chat(chat.username)
                logger.info(f"✅ UserBot joined via @{chat.username}")
                return True
            except Exception as e:
                logger.error(f"Join via username failed: {e}")
        
        # Try creating and using invite link
        try:
            invite_link = await bot.export_chat_invite_link(chat_id)
            await userbot.join_chat(invite_link)
            logger.info(f"✅ UserBot joined via invite link")
            return True
        except ChatAdminRequired:
            logger.error("❌ Bot needs admin rights to create invite link")
            return False
        except Exception as e:
            logger.error(f"Join via invite failed: {e}")
            return False
        
    except UserAlreadyParticipant:
        logger.info("✅ UserBot already participant")
        return True
    except Exception as e:
        logger.error(f"❌ Join chat error: {e}")
        return False

async def play_next_song(chat_id: int):
    """تشغيل الأغنية التالية في القائمة"""
    if not pytgcalls_available or not calls:
        logger.warning("⚠️ PyTgCalls not available")
        return False
    
    # Check queue
    if chat_id not in music_queue or not music_queue[chat_id]:
        # Queue empty - leave call
        try:
            await calls.leave_group_call(chat_id)
            if chat_id in currently_playing:
                del currently_playing[chat_id]
            logger.info(f"🔚 Queue empty, left chat {chat_id}")
        except Exception as e:
            logger.error(f"Leave call error: {e}")
        return False
    
    # Get next song
    next_song = music_queue[chat_id].pop(0)
    
    try:
        # Join and play
        await calls.join_group_call(
            chat_id,
            AudioPiped(next_song['url']),
        )
        
        currently_playing[chat_id] = next_song
        logger.info(f"▶️ Now playing: {next_song['title']}")
        
        # Notify in chat
        try:
            await bot.send_message(
                chat_id,
                f"▶️ **يتم التشغيل الآن:**\n🎵 {next_song['title']}"
            )
        except:
            pass
        
        return True
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Play error: {error_msg}")
        
        # Handle specific errors
        if "NO_ACTIVE_GROUP_CALL" in error_msg or "No active group call" in error_msg:
            logger.error("❌ No voice chat active!")
            try:
                await bot.send_message(
                    chat_id,
                    "❌ **لا توجد محادثة صوتية نشطة!**\n\n"
                    "ابدأ محادثة صوتية أولاً ثم جرب مرة أخرى."
                )
            except:
                pass
            return False
        
        # Try next song on error
        logger.info("Trying next song...")
        return await play_next_song(chat_id)

# Stream ended callback
if pytgcalls_available and calls:
    @calls.on_stream_end()
    async def on_stream_end(client: PyTgCalls, update: Update):
        """عند انتهاء الأغنية"""
        try:
            if isinstance(update, StreamAudioEnded):
                chat_id = update.chat_id
                logger.info(f"🔚 Stream ended in {chat_id}")
                
                # Notify
                if chat_id in currently_playing:
                    ended_song = currently_playing[chat_id]
                    try:
                        await bot.send_message(
                            chat_id,
                            f"✅ **انتهى تشغيل:**\n🎵 {ended_song['title']}"
                        )
                    except:
                        pass
                
                # Play next
                success = await play_next_song(chat_id)
                
                if not success:
                    try:
                        await bot.send_message(
                            chat_id,
                            "📭 **انتهت قائمة الانتظار**"
                        )
                    except:
                        pass
        except Exception as e:
            logger.error(f"Stream end handler error: {e}")

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
    """تحميل معلومات الأغنية من YouTube"""
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
    """تنسيق المدة"""
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
        [InlineKeyboardButton("➕ أضفني لقناتك/مجموعتك", 
            url=f"https://t.me/{bot_username}?startgroup=true")],
        [InlineKeyboardButton("📚 الأوامر", callback_data="help"),
         InlineKeyboardButton("ℹ️ حول", callback_data="about")]
    ])
    
    playback_status = "✅ التشغيل الفعلي متاح" if (userbot_available and pytgcalls_available) else "❌ التشغيل الفعلي غير متاح"
    
    await message.reply_text(
        f"🎵 **مرحباً {message.from_user.mention}!**\n\n"
        f"أنا بوت تشغيل الموسيقى في القنوات والمجموعات\n\n"
        f"**الحالة:** {playback_status}\n\n"
        f"**المميزات:**\n"
        f"✅ تشغيل فعلي في المحادثات الصوتية\n"
        f"✅ انضمام تلقائي للقنوات والمجموعات\n"
        f"✅ بحث في YouTube\n"
        f"✅ قوائم انتظار ذكية\n"
        f"✅ انتقال تلقائي بين الأغاني\n\n"
        f"**للبدء:**\n"
        f"1️⃣ أضفني لقناتك أو مجموعتك\n"
        f"2️⃣ اجعلني مشرف مع صلاحيات:\n"
        f"   • إدارة المحادثة الصوتية\n"
        f"   • إرسال الرسائل\n"
        f"   • دعوة المستخدمين\n"
        f"3️⃣ ابدأ محادثة صوتية/بث مباشر\n"
        f"4️⃣ استخدم `/play [اسم الأغنية]`\n\n"
        f"{'🎉 العميل المساعد سينضم وينضم تلقائياً!' if userbot_available else '⚠️ للتشغيل: أضف SESSION_STRING'}",
        reply_markup=keyboard
    )

@bot.on_message(filters.command("help"))
async def help_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    await message.reply_text(
        "📚 **دليل الاستخدام الكامل**\n\n"
        "**🎵 أوامر الموسيقى:**\n"
        "• `/play [أغنية]` - تشغيل من YouTube\n"
        "• `/pause` - إيقاف مؤقت\n"
        "• `/resume` - استئناف التشغيل\n"
        "• `/skip` - تخطي الأغنية الحالية\n"
        "• `/stop` - إيقاف وحذف القائمة\n"
        "• `/queue` - عرض قائمة الانتظار\n"
        "• `/current` - الأغنية الحالية\n\n"
        "**ℹ️ أوامر المعلومات:**\n"
        "• `/ping` - فحص السرعة\n"
        "• `/stats` - الإحصائيات\n\n"
        "**💡 للقنوات:**\n"
        "ابدأ بث صوتي مباشر ثم استخدم /play\n\n"
        "**💡 للمجموعات:**\n"
        "ابدأ محادثة صوتية ثم استخدم /play"
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
        f"▶️ **قيد التشغيل:** {len(currently_playing)}\n"
        f"📊 **الرسائل:** {stats['messages']}\n\n"
        f"{'🎉 **جاهز للتشغيل الفعلي!**' if (userbot_available and pytgcalls_available) else '⚠️ **أضف SESSION_STRING للتشغيل**'}"
    )

@bot.on_message(filters.command("stats"))
async def stats_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    await message.reply_text(
        f"📊 **إحصائيات البوت:**\n\n"
        f"📨 **الرسائل:** {stats['messages']}\n"
        f"⚡ **الأوامر:** {stats['commands']}\n"
        f"👥 **المستخدمين:** {len(stats['users'])}\n"
        f"💬 **المجموعات/القنوات:** {len(stats['groups'])}\n"
        f"▶️ **قيد التشغيل:** {len(currently_playing)}\n"
        f"📋 **في الانتظار:** {sum(len(q) for q in music_queue.values())}"
    )

@bot.on_message(filters.command(["play", "p"]) & (filters.group | filters.channel))
async def play_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    stats['groups'].add(message.chat.id)
    
    chat_id = message.chat.id
    
    logger.info(f"🎯 PLAY in chat {chat_id}")
    
    # Check availability
    if not userbot_available:
        return await message.reply_text(
            "❌ **العميل المساعد غير متاح!**\n\n"
            "اتصل بمطور البوت لإضافة SESSION_STRING"
        )
    
    if not pytgcalls_available:
        return await message.reply_text(
            "❌ **PyTgCalls غير متاح!**\n\n"
            "التشغيل الفعلي غير ممكن حالياً."
        )
    
    if len(message.command) < 2:
        return await message.reply_text(
            "❌ **الاستخدام:**\n"
            "`/play [اسم الأغنية أو رابط]`\n\n"
            "**أمثلة:**\n"
            "• `/play فيروز صباح الخير`\n"
            "• `/play Imagine Dragons Believer`"
        )
    
    query = " ".join(message.command[1:])
    
    # Progress message
    msg = await message.reply_text(
        "🔄 **جاري التحضير...**\n\n"
        "⏳ إضافة العميل المساعد..."
    )
    
    # Join chat/channel
    joined = await join_chat(chat_id)
    
    if not joined:
        return await msg.edit(
            "❌ **فشل انضمام العميل المساعد!**\n\n"
            "**تأكد من:**\n"
            "• البوت مشرف\n"
            "• صلاحية دعوة المستخدمين متاحة\n"
            "• القناة/المجموعة عامة أو البوت يملك صلاحية الدعوة"
        )
    
    await msg.edit(
        "🔄 **جاري التحضير...**\n\n"
        "✅ العميل المساعد جاهز\n"
        "⏳ البحث عن الأغنية..."
    )
    
    # Search song
    song_info = await download_song(query)
    
    if not song_info:
        return await msg.edit("❌ **لم أجد الأغنية!**")
    
    # Add to queue
    if chat_id not in music_queue:
        music_queue[chat_id] = []
    
    music_queue[chat_id].append(song_info)
    position = len(music_queue[chat_id])
    
    # If not playing, start
    if chat_id not in currently_playing:
        await msg.edit(
            "🔄 **جاري التحضير...**\n\n"
            "✅ العميل المساعد جاهز\n"
            "✅ تم العثور على الأغنية\n"
            "⏳ بدء التشغيل..."
        )
        
        success = await play_next_song(chat_id)
        
        if success:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⏸️ إيقاف", callback_data="pause"),
                 InlineKeyboardButton("⏭️ تخطي", callback_data="skip")],
                [InlineKeyboardButton("⏹️ إيقاف كامل", callback_data="stop"),
                 InlineKeyboardButton("📋 القائمة", callback_data="queue")]
            ])
            
            await msg.edit(
                f"▶️ **يتم التشغيل الآن:**\n\n"
                f"🎵 **{song_info['title']}**\n"
                f"👤 {song_info['uploader']}\n"
                f"⏱️ {format_duration(song_info['duration'])}\n"
                f"🔗 [YouTube]({song_info['webpage_url']})\n\n"
                f"👤 طلب بواسطة: {message.from_user.mention if message.from_user else 'مجهول'}\n"
                f"🤖 العميل انضم تلقائياً ✅",
                reply_markup=keyboard,
                disable_web_page_preview=False
            )
        else:
            await msg.edit(
                "❌ **فشل التشغيل!**\n\n"
                "**تأكد من:**\n"
                "• وجود محادثة صوتية/بث نشط\n"
                "• البوت والعميل مشرفين\n"
                "• صلاحيات إدارة المحادثة الصوتية"
            )
    else:
        # Add to queue
        await msg.edit(
            f"✅ **تمت الإضافة للقائمة #{position}**\n\n"
            f"🎵 {song_info['title']}\n"
            f"⏱️ {format_duration(song_info['duration'])}\n\n"
            f"سيتم تشغيلها بعد الأغنية الحالية"
        )

@bot.on_message(filters.command("pause") & (filters.group | filters.channel))
async def pause_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    if not pytgcalls_available:
        return await message.reply_text("❌ PyTgCalls غير متاح")
    
    try:
        await calls.pause_stream(message.chat.id)
        await message.reply_text("⏸️ **تم الإيقاف المؤقت**")
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {str(e)}")

@bot.on_message(filters.command("resume") & (filters.group | filters.channel))
async def resume_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    if not pytgcalls_available:
        return await message.reply_text("❌ PyTgCalls غير متاح")
    
    try:
        await calls.resume_stream(message.chat.id)
        await message.reply_text("▶️ **تم الاستئناف**")
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {str(e)}")

@bot.on_message(filters.command("skip") & (filters.group | filters.channel))
async def skip_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    chat_id = message.chat.id
    
    if chat_id not in currently_playing:
        return await message.reply_text("❌ لا يوجد شيء قيد التشغيل")
    
    skipped = currently_playing[chat_id]['title']
    await message.reply_text(f"⏭️ **تخطي:** {skipped}")
    
    await play_next_song(chat_id)

@bot.on_message(filters.command("stop") & (filters.group | filters.channel))
async def stop_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    chat_id = message.chat.id
    
    try:
        if pytgcalls_available:
            await calls.leave_group_call(chat_id)
        
        count = len(music_queue.get(chat_id, []))
        
        if chat_id in music_queue:
            music_queue[chat_id] = []
        if chat_id in currently_playing:
            del currently_playing[chat_id]
        
        await message.reply_text(f"⏹️ **تم الإيقاف!**\nحذف {count} أغنية")
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {str(e)}")

@bot.on_message(filters.command("queue") & (filters.group | filters.channel))
async def queue_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    chat_id = message.chat.id
    text = ""
    
    if chat_id in currently_playing:
        current = currently_playing[chat_id]
        text += f"▶️ **الآن:**\n🎵 {current['title']}\n\n"
    
    if chat_id in music_queue and music_queue[chat_id]:
        text += "📋 **القائمة:**\n\n"
        for i, song in enumerate(music_queue[chat_id][:10], 1):
            text += f"{i}. {song['title']}\n"
        
        if len(music_queue[chat_id]) > 10:
            text += f"\n_...و {len(music_queue[chat_id]) - 10} أخرى_"
    else:
        if not text:
            text = "📭 **القائمة فارغة**"
    
    await message.reply_text(text)

@bot.on_message(filters.command("current") & (filters.group | filters.channel))
async def current_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    chat_id = message.chat.id
    
    if chat_id not in currently_playing:
        return await message.reply_text("❌ لا يوجد شيء قيد التشغيل")
    
    song = currently_playing[chat_id]
    await message.reply_text(
        f"▶️ **قيد التشغيل:**\n\n"
        f"🎵 {song['title']}\n"
        f"👤 {song['uploader']}\n"
        f"⏱️ {format_duration(song['duration'])}\n"
        f"🔗 [YouTube]({song['webpage_url']})",
        disable_web_page_preview=False
    )

# Callbacks
@bot.on_callback_query()
async def callback_handler(client, callback_query):
    await callback_query.answer()

# Web server
async def health(request):
    return web.Response(text=f"OK")

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
        h1{{font-size:4em;margin:20px}}
        .status{{font-size:2em;color:#4ade80;margin:30px}}
        .info{{font-size:1.3em;margin:15px;background:rgba(255,255,255,0.1);
        padding:15px;border-radius:10px}}
    </style>
</head>
<body>
    <h1>🎵 Music Bot</h1>
    <div class="status">{'🎉 تشغيل فعلي!' if (userbot_available and pytgcalls_available) else '⚠️ بدون تشغيل'}</div>
    <div class="info">البوت: @{bot_username or 'Loading'}</div>
    <div class="info">UserBot: {'✅ متصل' if userbot_available else '❌'}</div>
    <div class="info">PyTgCalls: {'✅ جاهز' if pytgcalls_available else '❌'}</div>
    <div class="info">قيد التشغيل: {len(currently_playing)}</div>
    <div class="info">في الانتظار: {sum(len(q) for q in music_queue.values())}</div>
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
    logger.info("🎵 MUSIC BOT - FULL PLAYBACK MODE")
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
                logger.info("✅ PyTgCalls: STARTED")
                logger.info("🎉 FULL PLAYBACK MODE READY!")
            except Exception as e:
                logger.error(f"❌ PyTgCalls start error: {e}")
        else:
            logger.warning("⚠️ PyTgCalls: NOT AVAILABLE")
    else:
        logger.warning("⚠️ Add SESSION_STRING to enable playback")
    
    await start_web()
    
    logger.info("="*60)
    logger.info("✅ BOT READY!")
    logger.info(f"🔗 https://t.me/{me.username}")
    logger.info("="*60)
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    bot.run(main())
