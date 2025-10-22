"""State persistence for auto-resume functionality."""

import asyncio
import logging
from typing import Dict, Optional

from bot.core.player import player
from bot.core.queue import Track, queue_manager
from bot.persistence.storage import storage
from config import config

logger = logging.getLogger(__name__)


class StateManager:
    """Manage playback state persistence."""
    
    def __init__(self):
        self.save_task: Optional[asyncio.Task] = None
    
    async def initialize(self) -> None:
        """Initialize state manager."""
        await storage.initialize()
        logger.info("State manager initialized")
    
    async def save_state(self, chat_id: int) -> None:
        """Save playback state for a chat."""
        try:
            state = player.get_state(chat_id)
            if not state:
                return
            
            track = state["track"]
            save_data = {
                "chat_id": chat_id,
                "track": {
                    "id": track.id,
                    "title": track.title,
                    "duration": track.duration,
                    "url": track.url,
                    "file_path": track.file_path,
                    "requested_by": track.requested_by,
                    "requester_name": track.requester_name
                },
                "position": state.get("position", 0),
                "is_paused": state.get("is_paused", False)
            }
            
            await storage.set(f"state_{chat_id}", save_data)
            logger.debug(f"Saved state for chat {chat_id}")
            
        except Exception as e:
            logger.error(f"Failed to save state for {chat_id}: {e}")
    
    async def load_state(self, chat_id: int) -> Optional[Dict]:
        """Load playback state for a chat."""
        try:
            state = await storage.get(f"state_{chat_id}")
            return state
        except Exception as e:
            logger.error(f"Failed to load state for {chat_id}: {e}")
            return None
    
    async def clear_state(self, chat_id: int) -> None:
        """Clear saved state for a chat."""
        try:
            await storage.delete(f"state_{chat_id}")
            logger.debug(f"Cleared state for chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to clear state for {chat_id}: {e}")
    
    async def save_all_states(self) -> None:
        """Save states for all active chats."""
        for chat_id in player.active_chats:
            await self.save_state(chat_id)
        logger.info(f"Saved states for {len(player.active_chats)} chats")
    
    async def resume_all_playback(self) -> None:
        """Resume playback for all saved states."""
        try:
            states = await storage.get_all()
            
            for state_data in states:
                if not state_data or "chat_id" not in state_data:
                    continue
                
                chat_id = state_data["chat_id"]
                
                # Reconstruct track
                track_data = state_data.get("track")
                if not track_data:
                    continue
                
                track = Track(
                    id=track_data["id"],
                    title=track_data["title"],
                    duration=track_data["duration"],
                    url=track_data["url"],
                    file_path=track_data.get("file_path"),
                    requested_by=track_data.get("requested_by", 0),
                    requester_name=track_data.get("requester_name", "Bot")
                )
                
                # Add to queue and play
                queue = queue_manager.get_queue(chat_id)
                queue.add(track)
                
                # Resume playback
                position = state_data.get("position", 0)
                success = await player.play(chat_id, track, resume_from=position)
                
                if success:
                    logger.info(f"Resumed playback in {chat_id} from {position}s")
                    
                    # Send notification
                    from bot.client import bot_client
                    from bot.helpers.localization import get_text
                    
                    try:
                        await bot_client.send_message(
                            chat_id,
                            get_text(chat_id, "bot_restarted")
                        )
                    except:
                        pass
                
        except Exception as e:
            logger.error(f"Failed to resume playback: {e}")
    
    async def periodic_save(self) -> None:
        """Periodically save states."""
        while True:
            try:
                await asyncio.sleep(config.STATE_SAVE_INTERVAL)
                await self.save_all_states()
            except Exception as e:
                logger.error(f"Error in periodic save: {e}")

# Global instance
state_manager = StateManager()
