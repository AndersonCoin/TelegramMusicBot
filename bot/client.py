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

# Export for app.py
app = bot_client  # Alias for compatibility
