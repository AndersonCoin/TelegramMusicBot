"""Client initialization for bot and assistant."""

import logging

from pyrogram import Client
from pyrogram.enums import ParseMode

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

# Don't initialize PyTgCalls here, do it in app.py after clients start
call_client = None

logger.info("Clients created successfully")
