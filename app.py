"""Main application entry point."""

import asyncio
import logging
import signal
import sys
from typing import Optional

from aiohttp import web
from pyrogram import idle

from config import config
from bot.client import bot_client, user_client, call_client

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log")
    ]
)
logger = logging.getLogger(__name__)

# Health check server
health_app = web.Application()
state_manager: Optional['StateManager'] = None

async def health_check(request: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.Response(text="Bot is running!", status=200)

async def cleanup_handler(app: web.Application) -> None:
    """Cleanup on shutdown."""
    logger.info("Shutting down...")
    if state_manager:
        await state_manager.save_all_states()

async def start_bot() -> None:
    """Start the bot and assistant clients."""
    global state_manager
    
    # Validate configuration
    config.validate()
    
    logger.info("Starting bot...")
    
    # Initialize clients
    await bot_client.start()
    await user_client.start()
    await call_client.start()
    
    # Import here to avoid circular imports
    from bot.persistence.state import StateManager
    from bot.helpers.assistant import AssistantManager
    
    # Initialize state manager
    state_manager = StateManager()
    await state_manager.initialize()
    
    # Initialize assistant manager
    assistant_mgr = AssistantManager(bot_client, user_client)
    await assistant_mgr.initialize()
    # Set global reference
    from bot import helpers
    helpers.assistant.assistant_manager = assistant_mgr
    
    # Initialize player
    from bot.core.player import Player
    from bot import core
    core.player.player = Player(call_client)
    
    # Resume playback for all saved states
    await state_manager.resume_all_playback()
    
    # Start periodic tasks
    asyncio.create_task(state_manager.periodic_save())
    asyncio.create_task(cleanup_downloads())
    
    logger.info("Bot started successfully!")
    
    # Setup health check if needed
    if config.PORT:
        health_app.router.add_get("/", health_check)
        health_app.router.add_get("/health", health_check)
        health_app.on_cleanup.append(cleanup_handler)
        
        runner = web.AppRunner(health_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", config.PORT)
        await site.start()
        logger.info(f"Health check server running on port {config.PORT}")
    
    # Keep the bot running
    await idle()

async def cleanup_downloads() -> None:
    """Periodically clean up old download files."""
    while True:
        try:
            await asyncio.sleep(config.CLEANUP_INTERVAL)
            
            # Clean files older than 1 hour
            import time
            from pathlib import Path
            
            cutoff = time.time() - 3600
            for file in config.DOWNLOAD_DIR.glob("*"):
                if file.is_file() and file.stat().st_mtime < cutoff:
                    try:
                        file.unlink()
                        logger.debug(f"Cleaned up old file: {file}")
                    except Exception as e:
                        logger.error(f"Error cleaning file {file}: {e}")
                        
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")

def signal_handler(sig, frame):
    """Handle shutdown signals."""
    logger.info("Received shutdown signal")
    asyncio.create_task(shutdown())

async def shutdown():
    """Graceful shutdown."""
    if state_manager:
        await state_manager.save_all_states()
    sys.exit(0)

if __name__ == "__main__":
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run the bot
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
