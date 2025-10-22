
import asyncio
import logging
from pyrogram import idle
from aiohttp import web

from config import Config
from bot.client import app
from bot.persistence.state import auto_resume_all_states

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL, "INFO"),
    format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(Config.LOG_DIR / 'bot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

async def health_check(request):
    return web.Response(text="Bot is running!")

async def start_health_server():
    health_app = web.Application()
    health_app.router.add_get('/', health_check)
    runner = web.AppRunner(health_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', Config.PORT)
    await site.start()
    logger.info(f"✓ Health server started on port {Config.PORT}")

async def main():
    try:
        logger.info("="*50)
        logger.info("Starting Telegram Music Bot")
        logger.info("="*50)

        Config.validate()
        logger.info("✓ Configuration validated")

        await start_health_server()
        await app.start()
        await auto_resume_all_states()

        logger.info("="*50)
        logger.info("Bot is running! Press Ctrl+C to stop.")
        logger.info("="*50)

        await idle()

    except KeyboardInterrupt:
        logger.info("Stopping...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        await app.stop()
        logger.info("Goodbye!")

if __name__ == "__main__":
    asyncio.run(main())
