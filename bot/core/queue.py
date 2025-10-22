from typing import Dict, List, Optional
from dataclasses import dataclass, field

@dataclass
class Track:
    title: str
    duration: int
    requested_by: str
    file_path: str
    url: str
    thumbnail: Optional[str] = None
    meta: dict = field(default_factory=dict)

class ChatQueue:
    def __init__(self, chat_id: int):
        self.chat_id = chat_id
        self.queue: List[Track] = []
        self.current_track: Optional[Track] = None

    def add(self, track: Track) -> int:
        self.queue.append(track)
        return len(self.queue)

    def next(self) -> Optional[Track]:
        if not self.queue:
            self.current_track = None
            return None
        self.current_track = self.queue.pop(0)
        return self.current_track

    def clear(self):
        self.queue = []
        self.current_track = None

# Global queue manager
class QueueManager:
    def __init__(self):
        self.queues: Dict[int, ChatQueue] = {}

    def get_queue(self, chat_id: int) -> ChatQueue:
        if chat_id not in self.queues:
            self.queues[chat_id] = ChatQueue(chat_id)
        return self.queues[chat_id]

queue_manager = QueueManager()
