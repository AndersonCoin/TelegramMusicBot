import os
import logging
import asyncio
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
from dotenv import load_dotenv
from aiohttp import web

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Config
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 10000))

# Create bot
bot = Client(
    "bot",
    api_id=int(API_ID),
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Stats
message_count = 0

# ========== COMMAND HANDLERS (الأوامر أولاً!) ==========

@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    global message_count
    message_count += 1
    
    logger.info("🎯 START COMMAND!")
    
    try:
        await message.reply_text(
            "🎵 **مرحباً! أنا بوت الموسيقى**\n\n"
            "✅ البوت يعمل بشكل ممتاز!\n\n"
            "**الأوامر:**\n"
            "• /start - البداية\n"
            "• /test - اختبار\n"
            "• /ping - الحالة\n"
            "• /help - المساعدة\n"
            "• /id - معرفك\n\n"
            "جرب الأوامر الآن! 🚀"
        )
        logger.info("✅ START REPLY SENT!")
    except Exception as e:
        logger.error(f"❌ ERROR: {e}")

@bot.on_message(filters.command("test") & filters.private)
async def test_handler(client, message):
    global message_count
    message_count += 1
    
    logger.info("🎯 TEST COMMAND!")
    
    try:
        await message.reply_text(
            f"✅ **الاختبار نجح!**\n\n"
            f"🆔 **معرفك:** `{message.from_user.id}`\n"
            f"👤 **اسمك:** {message.from_user.first_name}\n"
            f"📊 **الرسائل:** {message_count}\n\n"
            f"البوت يعمل بشكل مثالي! 🎉"
        )
        logger.info("✅ TEST REPLY SENT!")
    except Exception as e:
        logger.error(f"❌ ERROR: {e}")

@bot.on_message(filters.command("ping") & filters.private)
async def ping_handler(client, message):
    global message_count
    message_count += 1
    
    logger.info("🎯 PING COMMAND!")
    
    import time
    start = time.time()
    
    try:
        msg = await message.reply_text("🏓 جاري الفحص...")
        end = time.time()
        latency = round((end - start) * 1000, 2)
        
        await msg.edit(
            f"🏓 **Pong!**\n\n"
            f"⚡ **السرعة:** `{latency}ms`\n"
            f"📊 **الرسائل:** {message_count}\n"
            f"✅ **الحالة:** نشط"
        )
        logger.info("✅ PING REPLY SENT!")
    except Exception as e:
        logger.error(f"❌ ERROR: {e}")

@bot.on_message(filters.command("help") & filters.private)
async def help_handler(client, message):
    global message_count
    message_count += 1
    
    logger.info("🎯 HELP COMMAND!")
    
    try:
        await message.reply_text(
            "📚 **المساعدة - قائمة الأوامر**\n\n"
            "**أوامر عامة:**\n"
            "• `/start` - بدء البوت\n"
            "• `/test` - اختبار البوت\n"
            "• `/ping` - فحص السرعة\n"
            "• `/id` - معرف المستخدم\n"
            "• `/stats` - الإحصائيات\n\n"
            "**أوامر المجموعات:**\n"
            "• `/play [أغنية]` - تشغيل أغنية\n"
            "• `/queue` - القائمة\n"
            "• `/stop` - إيقاف\n\n"
            "البوت جاهز للاستخدام! 🎵"
        )
        logger.info("✅ HELP REPLY SENT!")
    except Exception as e:
        logger.error(f"❌ ERROR: {e}")

@bot.on_message(filters.command("id"))
async def id_handler(client, message):
    global message_count
    message_count += 1
    
    logger.info("🎯 ID COMMAND!")
    
    try:
        text = f"**🆔 معلوماتك:**\n\n"
        text += f"👤 **معرفك:** `{message.from_user.id}`\n"
        text += f"📛 **اسمك:** {message.from_user.first_name}\n"
        
        if message.from_user.username:
            text += f"🔗 **يوزرك:** @{message.from_user.username}\n"
        
        if message.chat.type != "private":
            text += f"\n💬 **معرف المجموعة:** `{message.chat.id}`\n"
        
        await message.reply_text(text)
        logger.info("✅ ID REPLY SENT!")
    except Exception as e:
        logger.error(f"❌ ERROR: {e}")

@bot.on_message(filters.command("stats"))
async def stats_handler(client, message):
    global message_count
    message_count += 1
    
    logger.info("🎯 STATS COMMAND!")
    
    try:
        await message.reply_text(
            f"📊 **إحصائيات البوت:**\n\n"
            f"📨 **الرسائل:** {message_count}\n"
            f"✅ **الحالة:** نشط\n"
            f"🔋 **الإصدار:** 1.0.0"
        )
        logger.info("✅ STATS REPLY SENT!")
    except Exception as e:
        logger.error(f"❌ ERROR: {e}")

# Group commands
@bot.on_message(filters.command(["play", "p"]) & filters.group)
async def play_handler(client, message):
    global message_count
    message_count += 1
    
    logger.info("🎯 PLAY COMMAND in group!")
    
    try:
        if len(message.command) < 2:
            await message.reply_text("❌ الاستخدام: `/play [اسم الأغنية]`")
            return
        
        query = " ".join(message.command[1:])
        
        await message.reply_text(
            f"🎵 **تم استلام طلبك!**\n\n"
            f"🔍 الأغنية: {query}\n"
            f"👤 طلب بواسطة: {message.from_user.mention}\n\n"
            f"_يعمل البوت بشكل صحيح!_"
        )
        logger.info("✅ PLAY REPLY SENT!")
    except Exception as e:
        logger.error(f"❌ ERROR: {e}")

# Log all other messages (في النهاية!)
@bot.on_message(filters.text & ~filters.command([]))
async def log_other_messages(client, message):
    global message_count
    message_count += 1
    
    logger.info(f"💬 Text message from {message.from_user.id}: {message.text[:50]}")

# ========== WEB SERVER ==========

bot_username = None

async def health(request):
    return web.Response(text=f"OK - Messages: {message_count}")

async def index(request):
    global bot_username
    
    html = f"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Music Bot Status</title>
    <meta http-equiv="refresh" content="10">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        .container {{
            background: rgba(255,255,255,0.15);
            padding: 50px;
            border-radius: 30px;
            backdrop-filter: blur(20px);
            box-shadow: 0 20px 60px rgba(0,0,0,0.5);
            max-width: 600px;
            width: 100%;
            text-align: center;
        }}
        h1 {{ font-size: 5em; margin-bottom: 20px; }}
        .status {{
            font-size: 2.5em;
            color: #4ade80;
            font-weight: bold;
            margin: 30px 0;
        }}
        .info {{
            background: rgba(255,255,255,0.1);
            padding: 20px;
            border-radius: 15px;
            margin: 15px 0;
            font-size: 1.4em;
        }}
        .counter {{
            font-size: 3em;
            color: #4ade80;
            font-weight: bold;
            margin: 20px 0;
        }}
        a {{
            display: inline-block;
            margin-top: 30px;
            padding: 20px 50px;
            background: linear-gradient(135deg, #4ade80, #22c55e);
            color: white;
            text-decoration: none;
            border-radius: 50px;
            font-size: 1.5em;
            font-weight: bold;
            transition: transform 0.3s;
        }}
        a:hover {{ transform: scale(1.05); }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎵</h1>
        <div class="status">⚡ نشط</div>
        <div class="info">🤖 البوت: @{bot_username or 'AtheerAlsalafBot'}</div>
        <div class="counter">{message_count}</div>
        <div class="info">رسالة مستلمة</div>
        <a href="https://t.me/{bot_username or 'AtheerAlsalafBot'}">
            فتح البوت ←
        </a>
    </div>
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
    logger.info(f"✅ Web server on port {PORT}")

# ========== MAIN ==========

async def main():
    global bot_username
    
    logger.info("="*60)
    logger.info("🎵 STARTING MUSIC BOT")
    logger.info("="*60)
    
    # Start bot
    await bot.start()
    
    # Get info
    me = await bot.get_me()
    bot_username = me.username
    
    logger.info(f"✅ Bot: @{me.username}")
    logger.info(f"✅ ID: {me.id}")
    logger.info(f"✅ Name: {me.first_name}")
    
    # Start web
    await start_web()
    
    logger.info("="*60)
    logger.info("✅ BOT IS READY AND LISTENING!")
    logger.info(f"🔗 Open: https://t.me/{me.username}")
    logger.info("="*60)
    
    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    bot.run(main())
