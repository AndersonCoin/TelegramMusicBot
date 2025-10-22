"""Client initialization for bot and assistant."""

import logging
from typing import Optional

from pyrogram import Client
from pyrogram.enums import ParseMode
from pytgcalls import PyTgCalls

from config import config

logger = logging.getLogger(__name__)

# Initialize bot client
bot_client = Client(
    "music_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    plugins=dict(root="bot/plugins"),
    parse_mode=ParseMode.MARKDOWN
)

# Initialize user (assistant) client
user_client = Client(
    "assistant",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    session_string=config.SESSION_STRING
)

# Initialize PyTgCalls
call_client = PyTgCalls(user_client)

# Global references for easy access
bot: Optional[Client] = None
assistant: Optional[Client] = None
calls: Optional[PyTgCalls] = None

async def initialize_clients():
    """Initialize global client references and helpers."""
    global bot, assistant, calls
    bot = bot_client
    assistant = user_client
    calls = call_client
    
    # Start PyTgCalls
    await calls.start()
    
    # Initialize assistant manager
    from bot.helpers.assistant import AssistantManager
    import bot.helpers.assistant as assistant_module
    
    assistant_module.assistant_manager = AssistantManager(bot, assistant)
    await assistant_module.assistant_manager.initialize()
    
    logger.info("Clients initialized successfully")
