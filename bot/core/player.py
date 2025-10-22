"""Music player core functionality."""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional, Set

from pyrogram.types import Message
from pytgcalls import StreamType
from pytgcalls.types import AudioPiped, Update
from pytgcalls.types.stream import StreamAudioEnded
from pytgcalls.exceptions import NoActiveGroupCall, GroupCallNotFound

from bot.client import calls
from bot.core.queue import queue_manager, Track
from bot.helpers.formatting import formatting
from bot.helpers.keyboards import keyboards
from config import config

logger = logging.getLogger(__name__)


class Player:
    """Core player functionality."""
    
    def __init__(self):
        self.active_chats: Set[int] = set()
        self.now_playing_messages: Dict[int, Message] = {}
        self.progress_tasks: Dict[int, asyncio.Task] = {}
        self.playback_state: Dict[int, dict] = {}
        
        # Register handlers
        calls.on_stream_end(self._on_stream_end)
    
    async def join(self, chat_id: int) -> bool:
        """Join voice chat."""
        try:
            await calls.join_group_call(
                chat_id,
                AudioPiped("input.raw"),  # Dummy input
                stream_type=StreamType().pulse_stream
            )
            self.active_chats.add(chat_id)
            logger.info(f"Joined voice chat: {chat_id}")
            return True
            
        except NoActiveGroupCall:
            logger.error(f"No active voice chat in {chat_id}")
            return False
        except Exception as e:
            logger.error(f"Failed to join voice chat {chat_id}: {e}")
            return False
    
    async def leave(self, chat_id: int) -> bool:
        """Leave voice chat."""
        try:
            await calls.leave_group_call(chat_id)
            self.active_chats.discard(chat_id)
            
            # Cancel progress task
            if chat_id in self.progress_tasks:
                self.progress_tasks[chat_id].cancel()
                del self.progress_tasks[chat_id]
            
            # Clear state
            self.playback_state.pop(chat_id, None)
            
            logger.info(f"Left voice chat: {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to leave voice chat {chat_id}: {e}")
            return False
    
    async def play(
        self, 
        chat_id: int, 
        track: Track,
        resume_from: int = 0
    ) -> bool:
        """Play a track."""
        try:
            if not track.file_path or not Path(track.file_path).exists():
                logger.error(f"File not found: {track.file_path}")
                return False
            
            # Prepare ffmpeg args for resume
            additional_ffmpeg_args = []
            if resume_from > 0:
                additional_ffmpeg_args = ["-ss", str(resume_from)]
            
            # Join if not already in call
            if chat_id not in self.active_chats:
                if not await self.join(chat_id):
                    return False
            
            # Stream the audio
            await calls.change_stream(
                chat_id,
                AudioPiped(
                    track.file_path,
                    additional_ffmpeg_parameters=additional_ffmpeg_args
                )
            )
            
            # Update state
            self.playback_state[chat_id] = {
                "track": track,
                "position": resume_from,
                "is_paused": False
            }
            
            logger.info(f"Playing {track.title} in {chat_id} from {resume_from}s")
            return True
            
        except Exception as e:
            logger.error(f"Failed to play in {chat_id}: {e}")
            return False
    
    async def pause(self, chat_id: int) -> bool:
        """Pause playback."""
        try:
            await calls.pause_stream(chat_id)
            
            if chat_id in self.playback_state:
                self.playback_state[chat_id]["is_paused"] = True
            
            logger.info(f"Paused playback in {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to pause in {chat_id}: {e}")
            return False
    
    async def resume(self, chat_id: int) -> bool:
        """Resume playback."""
        try:
            await calls.resume_stream(chat_id)
            
            if chat_id in self.playback_state:
                self.playback_state[chat_id]["is_paused"] = False
            
            logger.info(f"Resumed playback in {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to resume in {chat_id}: {e}")
            return False
    
    async def skip(self, chat_id: int) -> Optional[Track]:
        """Skip to next track."""
        queue = queue_manager.get_queue(chat_id)
        next_track = queue.next()
        
        if next_track:
            await self.play(chat_id, next_track)
            return next_track
        else:
            await self.stop(chat_id)
            return None
    
    async def stop(self, chat_id: int) -> bool:
        """Stop playback and clear queue."""
        try:
            # Clear queue
            queue = queue_manager.get_queue(chat_id)
            queue.clear()
            
            # Leave voice chat
            await self.leave(chat_id)
            
            logger.info(f"Stopped playback in {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop in {chat_id}: {e}")
            return False
    
    async def set_volume(self, chat_id: int, volume: int) -> bool:
        """Set volume (1-200)."""
        try:
            volume = max(1, min(200, volume))
            await calls.change_volume_call(chat_id, volume)
            logger.info(f"Set volume to {volume} in {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to set volume in {chat_id}: {e}")
            return False
    
    async def _on_stream_end(self, client, update: Update):
        """Handle stream end event."""
        if isinstance(update, StreamAudioEnded):
            chat_id = update.chat_id
            logger.info(f"Stream ended in {chat_id}")
            
            # Auto-play next track
            await self.skip(chat_id)
    
    async def update_progress(self, chat_id: int, message: Message):
        """Update now playing message with progress."""
        try:
            start_time = asyncio.get_event_loop().time()
            state = self.playback_state.get(chat_id)
            
            if not state:
                return
            
            track = state["track"]
            initial_position = state.get("position", 0)
            
            while chat_id in self.active_chats:
                try:
                    if state.get("is_paused"):
                        await asyncio.sleep(config.PROGRESS_UPDATE_INTERVAL)
                        continue
                    
                    # Calculate elapsed time
                    elapsed = int(asyncio.get_event_loop().time() - start_time) + initial_position
                    
                    # Update state position
                    state["position"] = elapsed
                    
                    # Format progress
                    progress_bar = formatting.progress_bar(elapsed, track.duration)
                    elapsed_str = formatting.duration(elapsed)
                    total_str = formatting.duration(track.duration)
                    
                    # Build text
                    from bot.helpers.localization import get_text
                    text = get_text(
                        chat_id,
                        "now_playing",
                        title=track.title,
                        duration=total_str,
                        requester=track.requester_name,
                        progress_bar=progress_bar,
                        elapsed=elapsed_str,
                        total=total_str
                    )
                    
                    # Update message
                    await message.edit_text(
                        text,
                        reply_markup=keyboards.player_controls(
                            chat_id,
                            is_paused=state.get("is_paused", False)
                        )
                    )
                    
                except Exception as e:
                    logger.error(f"Error updating progress: {e}")
                
                await asyncio.sleep(config.PROGRESS_UPDATE_INTERVAL)
                
        except asyncio.CancelledError:
            logger.debug(f"Progress updater cancelled for {chat_id}")
        except Exception as e:
            logger.error(f"Error in progress updater: {e}")
    
    def start_progress_updater(self, chat_id: int, message: Message):
        """Start progress updater task."""
        # Cancel existing task if any
        if chat_id in self.progress_tasks:
            self.progress_tasks[chat_id].cancel()
        
        # Start new task
        self.progress_tasks[chat_id] = asyncio.create_task(
            self.update_progress(chat_id, message)
        )
        
        # Store message reference
        self.now_playing_messages[chat_id] = message
    
    def get_state(self, chat_id: int) -> Optional[dict]:
        """Get playback state for a chat."""
        return self.playback_state.get(chat_id)

# Global instance
player = Player()
