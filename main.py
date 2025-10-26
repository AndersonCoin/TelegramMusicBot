import os
import logging
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from dotenv import load_dotenv
from aiohttp import web

load_dotenv()

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Disable some verbose logs
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)

# Environment
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
SESSION_STRING = os.getenv("SESSION_STRING")
PORT = int(os.getenv("PORT", 10000))

if not all([API_ID, API_HASH, BOT_TOKEN]):
    logger.error("❌ Missing environment variables!")
    exit(1)

# Bot
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
    except Exception as e:
        logger.error(f"UserBot error: {e}")
        userbot = None
else:
    userbot = None

# Global stats
stats = {
    'messages': 0,
    'commands': 0,
    'users': set(),
    'groups': set()
}

# Bot info cache
bot_info_cache = None

# ============= COMMANDS =============

@bot.on_message(filters.command("start"))
async def start_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    stats['users'].add(message.from_user.id)
    
    logger.info(f"⭐ /start from user {message.from_user.id}")
    
    try:
        await message.reply_text(
            "🎵 **مرحباً! أنا بوت الموسيقى**\n\n"
            "✅ البوت يعمل بشكل ممتاز!\n\n"
            "**الأوامر المتاحة:**\n"
            "• /start - بدء البوت\n"
            "• /help - المساعدة\n"
            "• /ping - فحص الحالة\n"
            "• /test - اختبار\n"
            "• /id - معرفك\n\n"
            "**للمجموعات:**\n"
            "• /play [أغنية] - تشغيل\n"
            "• /queue - القائمة\n"
            "• /stop - إيقاف"
        )
        logger.info("✅ Replied to /start")
    except Exception as e:
        logger.error(f"❌ Start error: {e}")

@bot.on_message(filters.command("help"))
async def help_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    logger.info(f"📚 /help from user {message.from_user.id}")
    
    await message.reply_text(
        "📚 **قائمة الأوامر الكاملة:**\n\n"
        "**🎵 أوامر الموسيقى (في المجموعات):**\n"
        "• `/play [اسم الأغنية]` - تشغيل أغنية\n"
        "• `/pause` - إيقاف مؤقت\n"
        "• `/resume` - استئناف\n"
        "• `/skip` - تخطي\n"
        "• `/stop` - إيقاف كامل\n"
        "• `/queue` - عرض القائمة\n\n"
        "**ℹ️ أوامر عامة:**\n"
        "• `/ping` - فحص حالة البوت\n"
        "• `/stats` - الإحصائيات\n"
        "• `/id` - معرف المستخدم\n"
        "• `/test` - اختبار البوت\n\n"
        "**💡 كيف تستخدم البوت:**\n"
        "1. أضف البوت للمجموعة\n"
        "2. اجعله مشرف\n"
        "3. ابدأ محادثة صوتية\n"
        "4. استخدم `/play [اسم الأغنية]`"
    )

@bot.on_message(filters.command("ping"))
async def ping_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    logger.info(f"🏓 /ping from user {message.from_user.id}")
    
    import time
    start = time.time()
    msg = await message.reply_text("🏓 جاري الفحص...")
    end = time.time()
    latency = round((end - start) * 1000, 2)
    
    await msg.edit(
        f"🏓 **Pong!**\n\n"
        f"⚡ **السرعة:** `{latency}ms`\n"
        f"🤖 **البوت:** ✅ يعمل\n"
        f"👤 **UserBot:** {'✅ متصل' if userbot_available else '❌ غير متصل'}\n"
        f"📊 **الرسائل:** {stats['messages']}\n"
        f"👥 **المستخدمين:** {len(stats['users'])}"
    )

@bot.on_message(filters.command("test"))
async def test_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    logger.info(f"🧪 /test from user {message.from_user.id}")
    
    await message.reply_text(
        "✅ **الاختبار نجح!**\n\n"
        f"🆔 **معرفك:** `{message.from_user.id}`\n"
        f"👤 **اسمك:** {message.from_user.first_name}\n"
        f"📊 **إجمالي الرسائل:** {stats['messages']}\n"
        f"⚡ **الأوامر المنفذة:** {stats['commands']}\n\n"
        "البوت يعمل بشكل مثالي! 🎉"
    )

@bot.on_message(filters.command("id"))
async def id_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    text = f"**🆔 المعلومات:**\n\n"
    text += f"👤 **معرفك:** `{message.from_user.id}`\n"
    text += f"📛 **اسمك:** {message.from_user.first_name}\n"
    
    if message.from_user.username:
        text += f"🔗 **يوزرك:** @{message.from_user.username}\n"
    
    if message.chat.type != "private":
        text += f"\n💬 **معرف المجموعة:** `{message.chat.id}`\n"
        if message.chat.title:
            text += f"📝 **اسم المجموعة:** {message.chat.title}"
    
    await message.reply_text(text)

@bot.on_message(filters.command("stats"))
async def stats_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    await message.reply_text(
        f"📊 **إحصائيات البوت:**\n\n"
        f"📨 **إجمالي الرسائل:** {stats['messages']}\n"
        f"⚡ **الأوامر المنفذة:** {stats['commands']}\n"
        f"👥 **عدد المستخدمين:** {len(stats['users'])}\n"
        f"💬 **عدد المجموعات:** {len(stats['groups'])}\n"
        f"✅ **الحالة:** نشط\n"
        f"🔋 **UserBot:** {'متصل' if userbot_available else 'غير متصل'}"
    )

@bot.on_message(filters.command(["play", "p"]) & filters.group)
async def play_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    stats['groups'].add(message.chat.id)
    
    logger.info(f"🎵 /play in group {message.chat.id}")
    
    if len(message.command) < 2:
        await message.reply_text(
            "❌ **الاستخدام:**\n"
            "`/play [اسم الأغنية]`\n\n"
            "**مثال:**\n"
            "`/play فيروز صباح الخير`"
        )
        return
    
    query = " ".join(message.command[1:])
    
    await message.reply_text(
        f"🎵 **تم استلام طلبك!**\n\n"
        f"🔍 **الأغنية:** {query}\n"
        f"👤 **طلب بواسطة:** {message.from_user.mention}\n\n"
        f"_ملاحظة: التشغيل الفعلي يتطلب تفعيل PyTgCalls_"
    )

# Track all messages
@bot.on_message(filters.text)
async def track_messages(client, message: Message):
    stats['messages'] += 1
    
    if message.text and not message.text.startswith('/'):
        logger.info(f"💬 Message from {message.from_user.id}: {message.text[:50]}")

# ============= WEB SERVER =============

async def health_check(request):
    return web.Response(text=f"OK|Messages:{stats['messages']}")

async def index(request):
    global bot_info_cache
    
    try:
        if not bot_info_cache:
            if bot.is_connected:
                bot_info_cache = await bot.get_me()
        
        username = bot_info_cache.username if bot_info_cache else "Loading"
        
        html = f"""
<!DOCTYPE html>
<html lang="ar">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Music Bot Status</title>
    <meta http-equiv="refresh" content="10">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        .container {{
            background: rgba(255,255,255,0.1);
            padding: 50px;
            border-radius: 30px;
            backdrop-filter: blur(20px);
            box-shadow: 0 20px 60px rgba(0,0,0,0.5);
            max-width: 600px;
            width: 100%;
        }}
        h1 {{ 
            font-size: 4em; 
            text-align: center; 
            margin-bottom: 20px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}
        .status {{
            text-align: center;
            font-size: 2em;
            color: #4ade80;
            margin: 20px 0;
            font-weight: bold;
        }}
        .info {{
            background: rgba(255,255,255,0.1);
            padding: 15px;
            border-radius: 15px;
            margin: 10px 0;
            font-size: 1.2em;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
            margin: 30px 0;
        }}
        .stat-box {{
            background: rgba(255,255,255,0.1);
            padding: 20px;
            border-radius: 15px;
            text-align: center;
        }}
        .stat-number {{
            font-size: 2.5em;
            font-weight: bold;
            color: #4ade80;
        }}
        .stat-label {{
            font-size: 0.9em;
            margin-top: 5px;
            opacity: 0.8;
        }}
        .bot-link {{
            display: block;
            text-align: center;
            margin-top: 30px;
            padding: 18px;
            background: linear-gradient(135deg, #4ade80, #22c55e);
            color: white;
            text-decoration: none;
            border-radius: 50px;
            font-size: 1.4em;
            font-weight: bold;
            transition: all 0.3s;
        }}
        .bot-link:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(74,222,128,0.5);
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎵</h1>
        <div class="status">⚡ ONLINE</div>
        
        <div class="info">🤖 البوت: @{username}</div>
        <div class="info">👤 UserBot: {'✅ متصل' if userbot_available else '❌ غير متصل'}</div>
        
        <div class="stats">
            <div class="stat-box">
                <div class="stat-number">{stats['messages']}</div>
                <div class="stat-label">الرسائل</div>
            </div>
            <div class="stat-box">
                <div class="stat-number">{stats['commands']}</div>
                <div class="stat-label">الأوامر</div>
            </div>
            <div class="stat-box">
                <div class="stat-number">{len(stats['users'])}</div>
                <div class="stat-label">المستخدمين</div>
            </div>
            <div class="stat-box">
                <div class="stat-number">{len(stats['groups'])}</div>
                <div class="stat-label">المجموعات</div>
            </div>
        </div>
        
        <a href="https://t.me/{username}" class="bot-link">
            فتح البوت →
        </a>
    </div>
</body>
</html>
        """
        return web.Response(text=html, content_type='text/html')
    except Exception as e:
        logger.error(f"Web error: {e}")
        return web.Response(text=f"<h1>Loading... {str(e)}</h1>", content_type='text/html')

async def start_web_server():
    app_web = web.Application()
    app_web.router.add_get('/', index)
    app_web.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"✅ Web server on port {PORT}")

# ============= MAIN =============

async def main():
    global bot_info_cache
    
    try:
        logger.info("="*60)
        logger.info("🎵 MUSIC BOT STARTING")
        logger.info("="*60)
        
        # Start bot first
        await bot.start()
        bot_info_cache = await bot.get_me()
        logger.info(f"✅ Bot: @{bot_info_cache.username}")
        
        # Start userbot
        if userbot_available:
            await userbot.start()
            user_info = await userbot.get_me()
            logger.info(f"✅ UserBot: {user_info.first_name}")
        
        # Start web server last
        await start_web_server()
        
        logger.info("="*60)
        logger.info("✅ BOT READY - SEND /start TO TEST")
        logger.info("="*60)
        
        # Keep running
        await idle()
        
        # Cleanup
        await bot.stop()
        if userbot_available:
            await userbot.stop()
        
    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())
