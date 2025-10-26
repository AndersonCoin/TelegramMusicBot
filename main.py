import os
import logging
import asyncio
from pyrogram import Client, filters
from dotenv import load_dotenv
from aiohttp import web

load_dotenv()

# Simple logging
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

logger.info(f"API_ID: {API_ID}")
logger.info(f"BOT_TOKEN exists: {bool(BOT_TOKEN)}")

# Create bot
bot = Client(
    "bot",
    api_id=int(API_ID),
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Message counter
message_count = 0

# ========== HANDLERS ==========

@bot.on_message()
async def log_all_messages(client, message):
    global message_count
    message_count += 1
    logger.info(f"📨 MESSAGE #{message_count} received!")
    logger.info(f"   From: {message.from_user.id}")
    logger.info(f"   Chat: {message.chat.id}")
    logger.info(f"   Text: {message.text}")

@bot.on_message(filters.command("start"))
async def start_handler(client, message):
    logger.info("🎯 START COMMAND DETECTED!")
    
    try:
        await message.reply_text("✅ البوت يعمل! أرسل /test")
        logger.info("✅ REPLY SENT!")
    except Exception as e:
        logger.error(f"❌ ERROR SENDING REPLY: {e}")

@bot.on_message(filters.command("test"))
async def test_handler(client, message):
    logger.info("🎯 TEST COMMAND DETECTED!")
    
    try:
        await message.reply_text(
            f"✅ البوت يعمل بشكل ممتاز!\n\n"
            f"معرفك: {message.from_user.id}\n"
            f"الرسائل: {message_count}"
        )
        logger.info("✅ TEST REPLY SENT!")
    except Exception as e:
        logger.error(f"❌ ERROR: {e}")

@bot.on_message(filters.text)
async def echo_handler(client, message):
    logger.info(f"💬 Text message: {message.text}")
    
    if message.text and not message.text.startswith('/'):
        try:
            await message.reply_text(f"رسالتك: {message.text}")
        except:
            pass

# ========== WEB SERVER ==========

async def health(request):
    return web.Response(text=f"OK - Messages: {message_count}")

async def index(request):
    bot_username = "Loading..."
    
    try:
        if bot.is_connected:
            me = await bot.get_me()
            bot_username = me.username
    except:
        pass
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Bot Status</title>
    <meta http-equiv="refresh" content="5">
    <style>
        body {{
            font-family: Arial;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-align: center;
            padding: 50px;
        }}
        h1 {{ font-size: 4em; }}
        .status {{ font-size: 2em; color: #4ade80; margin: 30px; }}
        .info {{ font-size: 1.5em; margin: 20px; }}
    </style>
</head>
<body>
    <h1>🎵 Music Bot</h1>
    <div class="status">✅ ONLINE</div>
    <div class="info">Bot: @{bot_username}</div>
    <div class="info">Messages Received: {message_count}</div>
    <div class="info"><a href="https://t.me/{bot_username}" style="color: #4ade80;">Open Bot →</a></div>
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
    logger.info(f"✅ Web server on {PORT}")

# ========== MAIN ==========

async def main():
    logger.info("="*60)
    logger.info("STARTING BOT")
    logger.info("="*60)
    
    # Start bot
    await bot.start()
    
    # Get bot info
    me = await bot.get_me()
    logger.info(f"✅ Bot Username: @{me.username}")
    logger.info(f"✅ Bot ID: {me.id}")
    logger.info(f"✅ Bot Name: {me.first_name}")
    
    # Start web
    await start_web()
    
    logger.info("="*60)
    logger.info("BOT IS READY!")
    logger.info(f"Open: https://t.me/{me.username}")
    logger.info("="*60)
    
    # Wait forever
    await asyncio.Event().wait()

if __name__ == "__main__":
    bot.run(main())
