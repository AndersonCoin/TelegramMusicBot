"""State management for persistence."""

import asyncio
import logging
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from bot.persistence.storage import storage
from config import config

logger = logging.getLogger(__name__)


@dataclass
class PlaybackState:
    """Playback state for a chat."""
    chat_id: int
    track_id: str
    track_title: str
    track_path: str
    position: int  # Seconds
    timestamp: float  # When saved


class StateManager:
    """Manage playback states."""
    
    def __init__(self):
        self.states: Dict[int, PlaybackState] = {}
        self.save_task: Optional[asyncio.Task] = None
    
    async def initialize(self) -> None:
        """Initialize state manager."""
        # Load existing states
        all_states = await storage.get_all()
        for state_dict in all_states:
            try:
                state = PlaybackState(**state_dict)
                self.states[state.chat_id] = state
            except Exception as e:
                logger.error(f"Failed to load state: {e}")
    
    async def save_state(self, chat_id: int, state: PlaybackState) -> bool:
        """Save state for a chat."""
        try:
            self.states[chat_id] = state
            return await storage.set(
                f"state_{chat_id}",
                asdict(state)
            )
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            return False
    
    async def get_state(self, chat_id: int) -> Optional[PlaybackState]:
        """Get state for a chat."""
        return self.states.get(chat_id)
    
    async def delete_state(self, chat_id: int) -> bool:
        """Delete state for a chat."""
        try:
            self.states.pop(chat_id, None)
            return await storage.delete(f"state_{chat_id}")
        except Exception as e:
            logger.error(f"Failed to delete state: {e}")
            return False
    
    async def save_all_states(self) -> None:
        """Save all current states."""
        for chat_id, state in self.states.items():
            await self.save_state(chat_id, state)
    
    async def periodic_save(self) -> None:
        """Periodically save states."""
        while True:
            try:
                await asyncio.sleep(config.STATE_SAVE_INTERVAL)
                
                # Import here to avoid circular import
                from bot.core import player
                from bot.core.queue import queue_manager
                
                if not player:
                    continue
                
                # Save states for all playing chats
                for chat_id in player.is_playing:
                    if player.is_playing[chat_id]:
                        queue = queue_manager.get_queue(chat_id)
                        track = queue.current_track
                        
                        if track and track.file_path:
                            import time
                            state = PlaybackState(
                                chat_id=chat_id,
                                track_id=track.id,
                                track_title=track.title,
                                track_path=track.file_path,
                                position=track.position,
                                timestamp=time.time()
                            )
                            await self.save_state(chat_id, state)
                
            except Exception as e:
                logger.error(f"Error in periodic save: {e}")
    
    async def resume_all_playback(self) -> None:
        """Resume playback for all saved states."""
        if not self.states:
            return
        
        # Import here to avoid circular import
        from bot.client import bot_client
        from bot.helpers.localization import get_text
        
        for chat_id, state in self.states.items():
            try:
                # Send notification
                await bot_client.send_message(
                    chat_id,
                    get_text(chat_id, "bot_restarted")
                )
                
                # Resume playback
                # This will be handled by the /resume command or auto-resume
                
            except Exception as e:
                logger.error(f"Failed to resume for {chat_id}: {e}")
