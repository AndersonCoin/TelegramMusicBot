"""Playback state management."""

from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
from bot.persistence.storage import TinyDBBackend
from config import Config

@dataclass
class PlaybackState:
    """Represents playback state for a chat."""
    chat_id: int
    track_path: str
    position: int  # seconds
    track_data: Dict[str, Any]

class StateManager:
    """Manages playback states."""
    
    def __init__(self):
        self.storage = TinyDBBackend("data/states.json")
    
    async def save_state(self, state: PlaybackState):
        """Save playback state."""
        key = f"state_{state.chat_id}"
        await self.storage.set(key, asdict(state))
    
    async def get_state(self, chat_id: int) -> Optional[PlaybackState]:
        """Get playback state for chat."""
        key = f"state_{chat_id}"
        data = await self.storage.get(key)
        
        if data:
            return PlaybackState(**data)
        return None
    
    async def remove_state(self, chat_id: int):
        """Remove playback state."""
        key = f"state_{chat_id}"
        await self.storage.delete(key)
    
    async def get_all_states(self) -> List[PlaybackState]:
        """Get all saved states."""
        states = []
        all_data = await self.storage.get_all()
        
        for key, data in all_data.items():
            if key.startswith("state_"):
                states.append(PlaybackState(**data))
        
        return states
