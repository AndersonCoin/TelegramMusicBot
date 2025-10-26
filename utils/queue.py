from typing import Dict, List

# Global queue storage
queues: Dict[int, List[Dict]] = {}

def add_to_queue(chat_id: int, song_info: Dict) -> int:
    """Add song to queue and return position"""
    if chat_id not in queues:
        queues[chat_id] = []
    
    queues[chat_id].append(song_info)
    return len(queues[chat_id])

def get_queue(chat_id: int) -> List[Dict]:
    """Get queue for a chat"""
    return queues.get(chat_id, [])

def remove_from_queue(chat_id: int, index: int) -> bool:
    """Remove song from queue at index"""
    if chat_id in queues and 0 <= index < len(queues[chat_id]):
        queues[chat_id].pop(index)
        return True
    return False

def clear_queue(chat_id: int):
    """Clear entire queue for a chat"""
    if chat_id in queues:
        queues[chat_id] = []
