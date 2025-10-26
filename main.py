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

# PyTgCalls
pytgcalls_available = False
calls = None

if userbot_available:
    try:
        from pytgcalls import PyTgCalls
        from pytgcalls.types import MediaStream, AudioQuality
        from pytgcalls.exceptions import NoActiveGroupCall, AlreadyJoinedError
        
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
        # تحقق من وجود UserBot في المجموعة
        try:
            await userbot.get_chat_member(chat_id, "me")
            logger.info(f"✅ UserBot already in chat {chat_id}")
            return True
        except UserNotParticipant:
            pass
        
        # الحصول على رابط دعوة
        chat = await bot.get_chat(chat_id)
        
        # محاولة الانضمام عبر اسم المستخدم
        if chat.username:
            await userbot.join_chat(chat.username)
            logger.info(f"✅ UserBot joined via username: {chat.username}")
            return True
        
        # محاولة الانضمام عبر رابط دعوة
        try:
            invite_link = await bot.export_chat_invite_link(chat_id)
            await userbot.join_chat(invite_link)
            logger.info(f"✅ UserBot joined via invite link")
            return True
        except ChatAdminRequired:
            logger.error("❌ Bot needs admin rights to create invite link")
            return False
        
    except UserAlreadyParticipant:
        logger.info("✅ UserBot already in chat")
        return True
    except Exception as e:
        logger.error(f"❌ Error joining chat: {e}")
        return False

async def play_next_song(chat_id: int):
    """تشغيل الأغنية التالية"""
    if not pytgcalls_available or not calls:
        logger.warning("⚠️ PyTgCalls not available")
        return False
    
    if chat_id not in music_queue or not music_queue[chat_id]:
        # Queue empty, leave call
        try:
            await calls.leave_call(chat_id)
            if chat_id in currently_playing:
                del currently_playing[chat_id]
            logger.info(f"🔚 Queue empty, left chat {chat_id}")
        except:
            pass
        return False
    
    next_song = music_queue[chat_id].pop(0)
    
    try:
        # تشغيل الأغنية
        await calls.play(
            chat_id,
            MediaStream(
                next_song['url'],
                audio_parameters=AudioQuality.HIGH
            )
        )
        
        currently_playing[chat_id] = next_song
        logger.info(f"▶️ Now playing: {next_song['title']}")
        return True
        
    except NoActiveGroupCall:
        logger.error("❌ No active voice chat!")
        return False
    except AlreadyJoinedError:
        logger.info("ℹ️ Already in call, changing stream...")
        try:
            await calls.change_stream(
                chat_id,
                MediaStream(next_song['url'], audio_parameters=AudioQuality.HIGH)
            )
            currently_playing[chat_id] = next_song
            return True
        except Exception as e:
            logger.error(f"❌ Error changing stream: {e}")
            return False
    except Exception as e:
        logger.error(f"❌ Error playing: {e}")
        # Try next song
        await play_next_song(chat_id)
        return False

# Stream ended callback
if pytgcalls_available and calls:
    @calls.on_stream_end()
    async def on_stream_end(client, update):
        try:
            chat_id = update.chat_id
            logger.info(f"🔚 Stream ended in {chat_id}")
            
            # إرسال إشعار
            if chat_id in currently_playing:
                song = currently_playing[chat_id]
                try:
                    await bot.send_message(
                        chat_id,
                        f"✅ **انتهى تشغيل:**\n🎵 {song['title']}"
                    )
                except:
                    pass
            
            # تشغيل الأغنية التالية
            await play_next_song(chat_id)
            
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
        return "Live"
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
    
    status = "✅ جاهز للتشغيل" if (userbot_available and pytgcalls_available) else "⚠️ التشغيل محدود"
    
    await message.reply_text(
        f"🎵 **مرحباً {message.from_user.mention}!**\n\n"
        f"أنا بوت تشغيل الموسيقى في المجموعات\n\n"
        f"**الحالة:** {status}\n\n"
        f"**المميزات:**\n"
        f"✅ {'انضمام تلقائي للمجموعات' if userbot_available else 'يحتاج UserBot'}\n"
        f"✅ {'تشغيل فعلي من YouTube' if pytgcalls_available else 'عرض معلومات فقط'}\n"
        f"✅ قوائم انتظار ذكية\n"
        f"✅ تحكم كامل بالأزرار\n\n"
        f"**للبدء:**\n"
        f"1️⃣ أضفني لمجموعتك\n"
        f"2️⃣ اجعلني مشرف\n"
        f"3️⃣ ابدأ محادثة صوتية\n"
        f"4️⃣ استخدم `/play [اسم الأغنية]`\n\n"
        f"{'🎉 العميل المساعد سينضم تلقائياً!' if userbot_available else '⚠️ أضف SESSION_STRING لتفعيل التشغيل'}",
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
        f"🤖 **الانضمام التلقائي:** {'✅ مفعّل' if userbot_available else '❌ معطّل'}"
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
            "لا يمكن تشغيل الموسيقى بدون UserBot.\n"
            "اتصل بمطور البوت لتفعيل SESSION_STRING."
        )
        return
    
    if not pytgcalls_available:
        await message.reply_text(
            "❌ **PyTgCalls غير متاح!**\n\n"
            "التشغيل الفعلي غير ممكن حالياً."
        )
        return
    
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
    
    # Progress message
    msg = await message.reply_text(
        "🔄 **جاري التحضير...**\n\n"
        "1️⃣ التحقق من العميل المساعد..."
    )
    
    # إضافة UserBot للمجموعة تلقائياً
    joined = await join_chat(chat_id)
    
    if not joined:
        await msg.edit(
            "❌ **فشل انضمام العميل المساعد!**\n\n"
            "**الحلول:**\n"
            "• تأكد من أن البوت مشرف\n"
            "• أو أضف العميل المساعد يدوياً للمجموعة"
        )
        return
    
    await msg.edit(
        "🔄 **جاري التحضير...**\n\n"
        "1️⃣ ✅ العميل المساعد جاهز\n"
        "2️⃣ البحث عن الأغنية..."
    )
    
    # Download song
    song_info = await download_song(query)
    
    if not song_info:
        await msg.edit("❌ **لم أجد الأغنية!**")
        return
    
    await msg.edit(
        "🔄 **جاري التحضير...**\n\n"
        "1️⃣ ✅ العميل المساعد جاهز\n"
        "2️⃣ ✅ تم العثور على الأغنية\n"
        "3️⃣ إضافة للقائمة..."
    )
    
    # Add to queue
    if chat_id not in music_queue:
        music_queue[chat_id] = []
    
    music_queue[chat_id].append(song_info)
    position = len(music_queue[chat_id])
    
    # If not playing, start
    if chat_id not in currently_playing:
        await msg.edit(
            "🔄 **جاري التحضير...**\n\n"
            "1️⃣ ✅ العميل المساعد جاهز\n"
            "2️⃣ ✅ تم العثور على الأغنية\n"
            "3️⃣ ✅ تمت الإضافة للقائمة\n"
            "4️⃣ بدء التشغيل..."
        )
        
        success = await play_next_song(chat_id)
        
        if success:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⏸️ إيقاف", callback_data=f"pause_{chat_id}"),
                 InlineKeyboardButton("⏭️ تخطي", callback_data=f"skip_{chat_id}")],
                [InlineKeyboardButton("⏹️ إيقاف كامل", callback_data=f"stop_{chat_id}"),
                 InlineKeyboardButton("📋 القائمة", callback_data=f"queue_{chat_id}")]
            ])
            
            await msg.edit(
                f"▶️ **يتم التشغيل الآن:**\n\n"
                f"🎵 **{song_info['title']}**\n"
                f"👤 **القناة:** {song_info['uploader']}\n"
                f"⏱️ **المدة:** {format_duration(song_info['duration'])}\n"
                f"🔗 [YouTube]({song_info['webpage_url']})\n\n"
                f"👤 **طلب بواسطة:** {message.from_user.mention}\n"
                f"🤖 **العميل المساعد:** انضم تلقائياً ✅",
                reply_markup=keyboard,
                disable_web_page_preview=False
            )
        else:
            await msg.edit(
                "❌ **فشل التشغيل!**\n\n"
                "**تأكد من:**\n"
                "• وجود محادثة صوتية نشطة\n"
                "• البوت والعميل المساعد مشرفين\n"
                "• صلاحيات إدارة المحادثة الصوتية"
            )
    else:
        # Already playing, just add to queue
        await msg.edit(
            f"✅ **تمت الإضافة للقائمة!**\n\n"
            f"🎵 **{song_info['title']}**\n"
            f"#️⃣ **الموضع:** #{position}\n"
            f"⏱️ **المدة:** {format_duration(song_info['duration'])}\n\n"
            f"سيتم تشغيلها بعد الأغنية الحالية"
        )
    
    logger.info(f"✅ Song queued: {song_info['title']}")

@bot.on_message(filters.command("pause") & filters.group)
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

@bot.on_message(filters.command("resume") & filters.group)
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

@bot.on_message(filters.command("skip") & filters.group)
async def skip_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    if not pytgcalls_available:
        return await message.reply_text("❌ PyTgCalls غير متاح")
    
    chat_id = message.chat.id
    
    if chat_id not in currently_playing:
        return await message.reply_text("❌ لا يوجد شيء قيد التشغيل")
    
    skipped = currently_playing[chat_id]['title']
    
    await message.reply_text(f"⏭️ **تخطي:** {skipped}")
    await play_next_song(chat_id)

@bot.on_message(filters.command("stop") & filters.group)
async def stop_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    chat_id = message.chat.id
    
    try:
        if pytgcalls_available and calls:
            await calls.leave_call(chat_id)
        
        count = len(music_queue.get(chat_id, []))
        
        if chat_id in music_queue:
            music_queue[chat_id] = []
        if chat_id in currently_playing:
            del currently_playing[chat_id]
        
        await message.reply_text(
            f"⏹️ **تم الإيقاف!**\n\n"
            f"تم حذف {count} أغنية من القائمة."
        )
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {str(e)}")

@bot.on_message(filters.command("queue") & filters.group)
async def queue_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    chat_id = message.chat.id
    
    if chat_id not in music_queue or not music_queue[chat_id]:
        if chat_id in currently_playing:
            song = currently_playing[chat_id]
            await message.reply_text(
                f"▶️ **قيد التشغيل:**\n\n"
                f"🎵 {song['title']}\n"
                f"⏱️ {format_duration(song['duration'])}\n\n"
                f"📭 **القائمة فارغة**"
            )
        else:
            await message.reply_text("📭 **لا يوجد شيء في القائمة**")
        return
    
    text = ""
    
    if chat_id in currently_playing:
        current = currently_playing[chat_id]
        text += f"▶️ **قيد التشغيل:**\n🎵 {current['title']}\n\n"
    
    text += "📋 **قائمة الانتظار:**\n\n"
    
    for i, song in enumerate(music_queue[chat_id][:10], 1):
        text += f"**{i}.** {song['title']}\n⏱️ {format_duration(song['duration'])}\n\n"
    
    if len(music_queue[chat_id]) > 10:
        text += f"\n_...و {len(music_queue[chat_id]) - 10} أخرى_"
    
    await message.reply_text(text)

# Callbacks
@bot.on_callback_query()
async def callback_handler(client, callback_query):
    data = callback_query.data
    
    if data == "help":
        await callback_query.message.edit_text(
            "📚 **المساعدة:**\n\n"
            "/play - تشغيل أغنية\n"
            "/pause - إيقاف مؤقت\n"
            "/resume - استئناف\n"
            "/skip - تخطي\n"
            "/stop - إيقاف\n"
            "/queue - القائمة"
        )
    elif data == "about":
        await callback_query.message.edit_text(
            f"ℹ️ **حول البوت:**\n\n"
            f"🤖 البوت: @{bot_username}\n"
            f"🎵 انضمام تلقائي: {'✅' if userbot_available else '❌'}\n"
            f"⚡ تشغيل فعلي: {'✅' if pytgcalls_available else '❌'}"
        )
    
    await callback_query.answer()

# Web server
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
    <div class="status">⚡ نشط</div>
    <div class="info">البوت: @{bot_username or 'AtheerAlsalafBot'}</div>
    <div class="info">UserBot: {'✅ متصل' if userbot_available else '❌'}</div>
    <div class="info">PyTgCalls: {'✅ جاهز' if pytgcalls_available else '❌'}</div>
    <div class="info">الانضمام التلقائي: {'✅ مفعّل' if userbot_available else '❌'}</div>
    <div class="info">الرسائل: {stats['messages']}</div>
    <div class="info">قيد التشغيل: {len(currently_playing)}</div>
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
    logger.info("🎵 STARTING MUSIC BOT")
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
            await calls.start()
            logger.info("✅ PyTgCalls started")
    else:
        logger.warning("⚠️ Auto-join: DISABLED (no UserBot)")
    
    await start_web()
    
    logger.info("="*60)
    logger.info("✅ READY!")
    logger.info(f"🔗 https://t.me/{me.username}")
    logger.info("="*60)
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    bot.run(main())
