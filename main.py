import os
import logging
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from aiohttp import web
import yt_dlp
from typing import Dict, List

load_dotenv()

# Logging مفصل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Environment
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
SESSION_STRING = os.getenv("SESSION_STRING")
PORT = int(os.getenv("PORT", 10000))

if not all([API_ID, API_HASH, BOT_TOKEN]):
    logger.error("❌ Missing environment variables!")
    exit(1)

logger.info(f"API_ID: {API_ID}")
logger.info(f"BOT_TOKEN: {BOT_TOKEN[:10]}...")

# Bot client
bot = Client(
    "MusicBot",
    api_id=int(API_ID),
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

# UserBot
userbot_available = False
if SESSION_STRING:
    try:
        userbot = Client(
            "UserBot",
            api_id=int(API_ID),
            api_hash=API_HASH,
            session_string=SESSION_STRING,
            in_memory=True
        )
        userbot_available = True
        logger.info("✅ UserBot configured")
    except Exception as e:
        logger.error(f"❌ UserBot error: {e}")
        userbot = None
else:
    userbot = None
    logger.warning("⚠️ No SESSION_STRING")

# PyTgCalls
pytgcalls_available = False
calls = None

if userbot_available:
    try:
        from pytgcalls import PyTgCalls
        from pytgcalls.types import MediaStream, AudioQuality
        
        calls = PyTgCalls(userbot)
        pytgcalls_available = True
        logger.info("✅ PyTgCalls available")
    except ImportError as e:
        logger.warning(f"⚠️ PyTgCalls not available: {e}")
    except Exception as e:
        logger.error(f"❌ PyTgCalls error: {e}")

# Global data
music_queue: Dict[int, List[Dict]] = {}
currently_playing: Dict[int, Dict] = {}

# Message counter for debugging
message_count = 0

# Test handler - يجب أن يرد على أي رسالة
@bot.on_message(filters.text & filters.private)
async def echo_handler(client, message: Message):
    global message_count
    message_count += 1
    logger.info(f"📨 Message #{message_count} from {message.from_user.id}: {message.text}")
    
    # إذا لم يكن أمر، لا ترد
    if not message.text.startswith('/'):
        return

# Start command - بسيط جداً
@bot.on_message(filters.command("start"))
async def start_handler(client, message: Message):
    logger.info(f"🎯 START command from {message.from_user.id}")
    
    try:
        await message.reply_text(
            "✅ **البوت يعمل!**\n\n"
            "أرسل /help للمساعدة"
        )
        logger.info("✅ Start reply sent")
    except Exception as e:
        logger.error(f"❌ Error in start: {e}")

# Ping command
@bot.on_message(filters.command("ping"))
async def ping_handler(client, message: Message):
    logger.info(f"🎯 PING command from {message.from_user.id}")
    
    try:
        import time
        start = time.time()
        msg = await message.reply_text("🏓 Pong!")
        end = time.time()
        latency = round((end - start) * 1000, 2)
        
        userbot_status = "✅" if userbot_available else "❌"
        calls_status = "✅" if pytgcalls_available else "❌"
        
        await msg.edit(
            f"🏓 **Pong!**\n\n"
            f"⚡ Latency: `{latency}ms`\n"
            f"🤖 Bot: ✅ Online\n"
            f"👤 UserBot: {userbot_status}\n"
            f"🎵 PyTgCalls: {calls_status}\n"
            f"📊 Messages: {message_count}"
        )
        logger.info("✅ Ping reply sent")
    except Exception as e:
        logger.error(f"❌ Error in ping: {e}")

# Help command
@bot.on_message(filters.command("help"))
async def help_handler(client, message: Message):
    logger.info(f"🎯 HELP command from {message.from_user.id}")
    
    try:
        await message.reply_text(
            "📚 **الأوامر المتاحة:**\n\n"
            "/start - بدء البوت\n"
            "/ping - فحص الحالة\n"
            "/help - هذه الرسالة\n"
            "/test - اختبار البوت\n"
            "/play [أغنية] - تشغيل (في المجموعات)\n"
            "/stats - الإحصائيات"
        )
        logger.info("✅ Help reply sent")
    except Exception as e:
        logger.error(f"❌ Error in help: {e}")

# Test command
@bot.on_message(filters.command("test"))
async def test_handler(client, message: Message):
    logger.info(f"🎯 TEST command from {message.from_user.id}")
    
    try:
        await message.reply_text(
            "✅ **اختبار ناجح!**\n\n"
            f"🆔 معرفك: `{message.from_user.id}`\n"
            f"👤 اسمك: {message.from_user.first_name}\n"
            f"📊 عدد الرسائل: {message_count}"
        )
        logger.info("✅ Test reply sent")
    except Exception as e:
        logger.error(f"❌ Error in test: {e}")

# Stats command
@bot.on_message(filters.command("stats"))
async def stats_handler(client, message: Message):
    logger.info(f"🎯 STATS command from {message.from_user.id}")
    
    try:
        await message.reply_text(
            f"📊 **الإحصائيات:**\n\n"
            f"📨 الرسائل المستلمة: {message_count}\n"
            f"💬 المجموعات النشطة: {len(music_queue)}\n"
            f"▶️ قيد التشغيل: {len(currently_playing)}\n"
            f"📋 في الانتظار: {sum(len(q) for q in music_queue.values())}"
        )
        logger.info("✅ Stats reply sent")
    except Exception as e:
        logger.error(f"❌ Error in stats: {e}")

# YouTube downloader
async def download_song(query: str):
    try:
        logger.info(f"🔍 Searching for: {query}")
        loop = asyncio.get_event_loop()
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        def extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if query.startswith(('http://', 'https://')):
                    info = ydl.extract_info(query, download=False)
                else:
                    info = ydl.extract_info(f"ytsearch:{query}", download=False)
                    if 'entries' in info and info['entries']:
                        info = info['entries'][0]
                return info
        
        info = await loop.run_in_executor(None, extract)
        
        if not info:
            logger.warning("⚠️ No song found")
            return None
        
        logger.info(f"✅ Found: {info.get('title', 'Unknown')}")
        
        return {
            'title': info.get('title', 'Unknown'),
            'url': info.get('url'),
            'duration': info.get('duration', 0),
            'thumbnail': info.get('thumbnail', ''),
            'webpage_url': info.get('webpage_url', ''),
            'uploader': info.get('uploader', 'Unknown')
        }
    except Exception as e:
        logger.error(f"❌ Download error: {e}")
        return None

# Format duration
def format_duration(seconds):
    if not seconds:
        return "Live"
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d}" if hours else f"{mins:02d}:{secs:02d}"

# Play command - للمجموعات فقط
@bot.on_message(filters.command(["play", "p"]) & filters.group)
async def play_handler(client, message: Message):
    logger.info(f"🎯 PLAY command in {message.chat.id}")
    
    try:
        if not userbot_available:
            await message.reply_text(
                "❌ **UserBot غير متاح!**\n"
                "لا يمكن تشغيل الموسيقى حالياً."
            )
            return
        
        if len(message.command) < 2:
            await message.reply_text(
                "❌ **الاستخدام:**\n"
                "`/play [اسم الأغنية]`\n\n"
                "**مثال:**\n"
                "`/play Believer`"
            )
            return
        
        query = " ".join(message.command[1:])
        chat_id = message.chat.id
        
        msg = await message.reply_text("🔍 **جاري البحث...**")
        
        song_info = await download_song(query)
        
        if not song_info:
            await msg.edit("❌ **لم أجد الأغنية!**")
            return
        
        # Add to queue
        if chat_id not in music_queue:
            music_queue[chat_id] = []
        
        music_queue[chat_id].append(song_info)
        position = len(music_queue[chat_id])
        
        await msg.edit(
            f"✅ **تمت الإضافة للقائمة!**\n\n"
            f"🎵 **الأغنية:** {song_info['title']}\n"
            f"👤 **القناة:** {song_info['uploader']}\n"
            f"⏱️ **المدة:** {format_duration(song_info['duration'])}\n"
            f"#️⃣ **الموضع:** #{position}\n\n"
            f"_ملاحظة: التشغيل الفعلي يتطلب PyTgCalls_"
        )
        
        logger.info(f"✅ Song added to queue in {chat_id}")
        
    except Exception as e:
        logger.error(f"❌ Error in play: {e}")
        await message.reply_text(f"❌ خطأ: {str(e)}")

# Queue command
@bot.on_message(filters.command("queue") & filters.group)
async def queue_handler(client, message: Message):
    logger.info(f"🎯 QUEUE command in {message.chat.id}")
    
    try:
        chat_id = message.chat.id
        
        if chat_id not in music_queue or not music_queue[chat_id]:
            await message.reply_text("📭 **القائمة فارغة**")
            return
        
        text = "📋 **قائمة الانتظار:**\n\n"
        
        for i, song in enumerate(music_queue[chat_id][:10], 1):
            text += f"{i}. {song['title']}\n"
        
        if len(music_queue[chat_id]) > 10:
            text += f"\n_...و {len(music_queue[chat_id]) - 10} أخرى_"
        
        await message.reply_text(text)
        
    except Exception as e:
        logger.error(f"❌ Error in queue: {e}")

# Web server
async def health_check(request):
    return web.Response(text=f"✅ Bot Online | Messages: {message_count}")

async def index(request):
    try:
        bot_info = await bot.get_me()
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Music Bot</title>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="5">
    <style>
        body {{
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
        }}
        .container {{
            background: rgba(255,255,255,0.1);
            padding: 40px;
            border-radius: 20px;
            backdrop-filter: blur(10px);
            text-align: center;
        }}
        h1 {{ font-size: 3em; margin: 0; }}
        .status {{ color: #4ade80; font-size: 1.5em; margin: 20px 0; }}
        .info {{ margin: 10px 0; font-size: 1.2em; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎵 Music Bot</h1>
        <div class="status">✅ ONLINE</div>
        <div class="info">Bot: @{bot_info.username}</div>
        <div class="info">UserBot: {'✅' if userbot_available else '❌'}</div>
        <div class="info">PyTgCalls: {'✅' if pytgcalls_available else '❌'}</div>
        <div class="info">Messages Received: {message_count}</div>
        <div class="info">Active Chats: {len(music_queue)}</div>
        <p style="margin-top: 30px;">
            <a href="https://t.me/{bot_info.username}" 
               style="color: #4ade80; text-decoration: none; font-size: 1.2em;">
                Start Bot →
            </a>
        </p>
    </div>
</body>
</html>
        """
        return web.Response(text=html, content_type='text/html')
    except Exception as e:
        logger.error(f"Web error: {e}")
        return web.Response(text=f"<h1>Error: {str(e)}</h1>", content_type='text/html')

async def start_web_server():
    app_web = web.Application()
    app_web.router.add_get('/', index)
    app_web.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"✅ Web server started on port {PORT}")

# Main function
async def main():
    try:
        logger.info("="*70)
        logger.info("🎵 MUSIC BOT STARTING")
        logger.info("="*70)
        
        # Start web server
        await start_web_server()
        logger.info("✅ Web server running")
        
        # Start bot
        await bot.start()
        bot_info = await bot.get_me()
        logger.info(f"✅ Bot started: @{bot_info.username} (ID: {bot_info.id})")
        
        # Start userbot
        if userbot_available:
            await userbot.start()
            user_info = await userbot.get_me()
            logger.info(f"✅ UserBot started: {user_info.first_name} (ID: {user_info.id})")
            
            # Start PyTgCalls
            if pytgcalls_available and calls:
                await calls.start()
                logger.info("✅ PyTgCalls started")
        
        logger.info("="*70)
        logger.info("✅ ALL SYSTEMS READY - BOT IS LISTENING")
        logger.info("="*70)
        logger.info("Send /start to the bot to test!")
        
        # Keep running
        await idle()
        
        # Cleanup
        logger.info("Shutting down...")
        await bot.stop()
        
        if userbot_available:
            if pytgcalls_available and calls:
                await calls.stop()
            await userbot.stop()
        
        logger.info("Bot stopped")
        
    except Exception as e:
        logger.error(f"❌ CRITICAL ERROR: {e}", exc_info=True)
        exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
