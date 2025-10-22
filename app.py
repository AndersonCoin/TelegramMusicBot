"""Main application entry point."""

import asyncio
import logging
import signal
from aiohttp import web
from bot.client import BotClient
from config import Config

# Configure logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Global bot instance
bot_client: BotClient = None

async def health_check(request):
    """Health check endpoint."""
    return web.Response(text="Bot is running!", status=200)

async def start_web_server():
    """Start health check web server."""
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", Config.PORT)
    await site.start()
    logger.info(f"Health server started on port {Config.PORT}")
    return runner

async def shutdown(runner):
    """Graceful shutdown handler."""
    logger.info("Shutting down...")
    if bot_client:
        await bot_client.stop()
    if runner:
        await runner.cleanup()

async def main():
    """Main application loop."""
    global bot_client
    
    # Initialize bot client
    bot_client = BotClient()
    
    # Start bot
    await bot_client.start()
    logger.info("Bot started successfully")
    
    # Start web server
    runner = await start_web_server()
    
    # Setup signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig, lambda: asyncio.create_task(shutdown(runner))
        )
    
    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
