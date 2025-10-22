"""Queue management system."""

import asyncio
import random
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

@dataclass
class Track:
    """Represents a track in the queue."""
    url: str
    title: str
    duration: int
    requester_id: int
    requester_name: str
    file_path: Optional[str] = None
    thumbnail: Optional[str] = None
    
@dataclass
class ChatQueue:
    """Queue for a specific chat."""
    chat_id: int
    tracks: List[Track] = field(default_factory=list)
    current_index: int = -1
    loop_mode: str = "off"  # off, track, queue
    
    def add(self, track: Track) -> int:
        """Add track to queue."""
        self.tracks.append(track)
        return len(self.tracks)
    
    def get_current(self) -> Optional[Track]:
        """Get current track."""
        if 0 <= self.current_index < len(self.tracks):
            return self.tracks[self.current_index]
        return None
    
    def next(self) -> Optional[Track]:
        """Move to next track."""
        if not self.tracks:
            return None
            
        if self.loop_mode == "track" and self.current_index >= 0:
            return self.tracks[self.current_index]
            
        self.current_index += 1
        
        if self.current_index >= len(self.tracks):
            if self.loop_mode == "queue":
                self.current_index = 0
            else:
                return None
                
        return self.tracks[self.current_index]
    
    def remove(self, index: int) -> bool:
        """Remove track at index."""
        if 0 <= index < len(self.tracks):
            self.tracks.pop(index)
            if index <= self.current_index:
                self.current_index -= 1
            return True
        return False
    
    def clear(self):
        """Clear the queue."""
        self.tracks.clear()
        self.current_index = -1
    
    def shuffle(self):
        """Shuffle remaining tracks."""
        if self.current_index + 1 < len(self.tracks):
            remaining = self.tracks[self.current_index + 1:]
            random.shuffle(remaining)
            self.tracks[self.current_index + 1:] = remaining
    
    def move(self, old_index: int, new_index: int) -> bool:
        """Move track from old to new position."""
        if (0 <= old_index < len(self.tracks) and 
            0 <= new_index < len(self.tracks)):
            track = self.tracks.pop(old_index)
            self.tracks.insert(new_index, track)
            return True
        return False

class QueueManager:
    """Global queue manager."""
    
    def __init__(self):
        self._queues: Dict[int, ChatQueue] = {}
        self._locks: Dict[int, asyncio.Lock] = {}
    
    def get_queue(self, chat_id: int) -> ChatQueue:
        """Get or create queue for chat."""
        if chat_id not in self._queues:
            self._queues[chat_id] = ChatQueue(chat_id)
            self._locks[chat_id] = asyncio.Lock()
        return self._queues[chat_id]
    
    async def get_lock(self, chat_id: int) -> asyncio.Lock:
        """Get lock for chat queue."""
        if chat_id not in self._locks:
            self._locks[chat_id] = asyncio.Lock()
        return self._locks[chat_id]
    
    def remove_queue(self, chat_id: int):
        """Remove queue for chat."""
        self._queues.pop(chat_id, None)
        self._locks.pop(chat_id, None)

# Global instance
queue_manager = QueueManager()
