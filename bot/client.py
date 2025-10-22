"""Bot and assistant client initialization."""

import logging
from pathlib import Path
from pyrogram import Client
from pyrogram.enums import ParseMode
from pytgcalls import PyTgCalls
from config import Config
from bot.core.player import Player
from bot.persistence.state import StateManager

logger = logging.getLogger(__name__)

class BotClient:
    """Main bot client manager."""
    
    def __init__(self):
        """Initialize bot components."""
        # Bot client
        self.bot = Client(
            "music_bot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            plugins=dict(root="bot/plugins"),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Assistant client
        self.assistant = Client(
            "assistant",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            session_string=Config.SESSION_STRING
        )
        
        # PyTgCalls
        self.pytgcalls = PyTgCalls(self.assistant)
        
        # Core components
        self.player = Player(self)
        self.state_manager = StateManager()
        
        # Store in bot for plugin access
        self.bot.music = self
        
    async def start(self):
        """Start all clients."""
        await self.bot.start()
        await self.assistant.start()
        await self.pytgcalls.start()
        
        # Get assistant info
        me = await self.assistant.get_me()
        self.assistant_username = me.username
        self.assistant_id = me.id
        
        logger.info(f"Bot started as @{(await self.bot.get_me()).username}")
        logger.info(f"Assistant started as @{self.assistant_username}")
        
        # Resume interrupted playbacks
        await self.player.resume_all_playbacks()
        
    async def stop(self):
        """Stop all clients."""
        await self.player.stop_all()
        await self.pytgcalls.stop()
        await self.assistant.stop()
        await self.bot.stop()
