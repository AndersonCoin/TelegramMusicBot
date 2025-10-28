import os
import logging
import asyncio
from dotenv import load_dotenv
from aiohttp import web
from pyrogram import Client, filters
from pyrogram.types import Message

# Load environment variables
load_dotenv()

# --- Basic Configuration ---
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 8080))

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

# --- Basic Sanity Checks ---
if not all([API_ID, API_HASH, BOT_TOKEN]):
    logger.critical("CRITICAL: API_ID, API_HASH, or BOT_TOKEN is missing from environment variables!")
    exit(1)

logger.info("Configuration seems OK.")

# --- Pyrogram Client Initialization ---
try:
    bot = Client(
        "bot_session",
        api_id=int(API_ID),
        api_hash=API_HASH,
        bot_token=BOT_TOKEN
    )
    logger.info("Pyrogram client initialized.")
except Exception as e:
    logger.critical(f"CRITICAL: Failed to initialize Pyrogram client: {e}")
    exit(1)

# --- Simple Command Handler for Testing ---
@bot.on_message(filters.command("ping"))
async def ping_handler(client: Client, message: Message):
    """A simple handler to check if the bot is responsive."""
    logger.info(f"Received /ping command from {message.from_user.id}")
    try:
        await message.reply_text("Pong! 🏓\nI am alive and responding.")
        logger.info("Successfully replied to /ping command.")
    except Exception as e:
        logger.error(f"Error replying to /ping: {e}")


# --- Web Server for Hosting Platforms ---
async def run_web_server():
    """Starts the aiohttp web server as a background task."""
    app = web.Application()
    
    async def health_check(request):
        logger.info("Web server health check endpoint was hit.")
        return web.Response(text="OK", status=200)
        
    app.router.add_get("/", health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    
    try:
        await site.start()
        logger.info(f"✅ Web server started successfully on port {PORT}.")
    except Exception as e:
        logger.error(f"❌ Failed to start web server on port {PORT}: {e}")


# --- Main Application Logic ---
async def main():
    logger.info("Starting main application function...")

    # Start the web server as a background task
    # This is crucial for hosting platforms like Render
    web_server_task = asyncio.create_task(run_web_server())
    logger.info("Web server task created.")

    try:
        # Start the Pyrogram client
        logger.info("Attempting to start the Pyrogram bot client...")
        await bot.start()
        bot_info = await bot.get_me()
        logger.info(f"✅ Bot @{bot_info.username} successfully started and connected to Telegram.")

        # This will keep the application running indefinitely
        logger.info("🚀 Application is now running. Waiting for updates...")
        await asyncio.Event().wait()

    except Exception as e:
        logger.critical(f"CRITICAL: An error occurred during bot startup: {e}", exc_info=True)
    finally:
        logger.info("Shutting down...")
        if bot.is_connected:
            await bot.stop()
        web_server_task.cancel()


if __name__ == "__main__":
    logger.info("Application starting from __main__...")
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Application shut down by user.")
