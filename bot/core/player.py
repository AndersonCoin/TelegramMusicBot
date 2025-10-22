import asyncio
import logging
import time
from pytgcalls import StreamType
from pytgcalls.types.input_stream import AudioPiped
from pytgcalls.exceptions import NoActiveGroupCall

from bot.client import app
from bot.core.queue import queue_manager, Track
from bot.persistence.state import save_playback_state, clear_playback_state
from bot.helpers.keyboards import get_player_keyboard
from bot.helpers.formatting import create_progress_bar

logger = logging.getLogger(__name__)

class Player:
    def __init__(self):
        self.updaters: dict[int, asyncio.Task] = {}
        self.start_times: dict[int, float] = {}

    async def play(self, chat_id: int, track: Track, resume_from: int = 0):
        try:
            additional_params = f"-ss {resume_from}" if resume_from > 0 else ""
            await app.call.join_group_call(
                chat_id,
                AudioPiped(track.file_path, additional_ffmpeg_parameters=additional_params),
                stream_type=StreamType().pulse_stream
            )
            self.start_times[chat_id] = time.time() - resume_from
            queue = queue_manager.get_queue(chat_id)
            queue.current_track = track
            await self.start_progress_updater(chat_id, track.meta['now_playing_message_id'])
            return True
        except NoActiveGroupCall:
            logger.warning(f"No active group call in {chat_id}")
            return False
        except Exception as e:
            logger.error(f"Error in play: {e}", exc_info=True)
            return False

    async def pause(self, chat_id: int):
        await app.call.pause_stream(chat_id)
        if chat_id in self.updaters:
            self.updaters[chat_id].cancel()

    async def resume(self, chat_id: int):
        await app.call.resume_stream(chat_id)
        queue = queue_manager.get_queue(chat_id)
        if queue.current_track:
            await self.start_progress_updater(chat_id, queue.current_track.meta['now_playing_message_id'])

    async def stop(self, chat_id: int):
        if chat_id in self.updaters:
            self.updaters[chat_id].cancel()
        
        queue_manager.get_queue(chat_id).clear()
        clear_playback_state(chat_id)
        await app.call.leave_group_call(chat_id)

    async def skip(self, chat_id: int):
        if chat_id in self.updaters:
            self.updaters[chat_id].cancel()

        queue = queue_manager.get_queue(chat_id)
        next_track = queue.next()

        if not next_track:
            await self.stop(chat_id)
            return None
        
        await self.play(chat_id, next_track)
        return next_track

    async def start_progress_updater(self, chat_id: int, message_id: int):
        if chat_id in self.updaters:
            self.updaters[chat_id].cancel()

        async def updater():
            while True:
                await asyncio.sleep(10)
                queue = queue_manager.get_queue(chat_id)
                track = queue.current_track
                if not track: break

                played = time.time() - self.start_times.get(chat_id, 0)
                if played > track.duration: played = track.duration

                progress = create_progress_bar(int(played), track.duration)
                text = (
                    f"▶️ **Now Playing:**\n{track.title}\n\n"
                    f"👤 **Requested by:** {track.requested_by}\n\n"
                    f"`{progress}`"
                )
                try:
                    await app.bot.edit_message_text(
                        chat_id,
                        message_id,
                        text,
                        reply_markup=get_player_keyboard(chat_id)
                    )
                    await save_playback_state(chat_id, track.file_path, int(played), track.meta)
                except Exception:
                    break # Message deleted or other error
        
        self.updaters[chat_id] = asyncio.create_task(updater())

player = Player()
