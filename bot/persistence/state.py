import asyncio
import logging
from bot.persistence.storage import playback_storage
from bot.core.player import player

logger = logging.getLogger(__name__)

async def save_playback_state(chat_id, track_path, position, track_meta):
    state = {
        'track_path': track_path,
        'position': position,
        'meta': track_meta
    }
    playback_storage.set(str(chat_id), state)

def get_playback_state(chat_id):
    return playback_storage.get(str(chat_id))

def clear_playback_state(chat_id):
    playback_storage.remove(str(chat_id))

async def auto_resume_all_states():
    all_states = playback_storage.all()
    if not all_states:
        logger.info("No saved states to resume.")
        return

    logger.info(f"Found {len(all_states)} saved states. Attempting to resume...")
    for item in all_states:
        chat_id = int(item['key'])
        state = item['value']
        
        from bot.helpers.localization import get_text
        from bot.client import app
        
        try:
            await app.bot.send_message(chat_id, get_text(chat_id, "bot_restarted_resuming"))
            await player.play(
                chat_id=chat_id,
                file_path=state['track_path'],
                resume_from=state['position'],
                track_meta=state['meta']
            )
            # Give some time between joins to avoid flooding
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Failed to auto-resume for chat {chat_id}: {e}")
            clear_playback_state(chat_id)
