"""Music player core functionality."""

import asyncio
import logging
from typing import Dict, Optional, Callable
from pathlib import Path

from pyrogram import Client
from pyrogram.types import Message
from pytgcalls import PyTgCalls
from pytgcalls.types import AudioPiped, StreamAudioEnded
from pytgcalls.exceptions import NoActiveGroupCall, AlreadyJoinedError

from bot.core.queue import queue_manager, Track
from bot.helpers.formatting import formatting
from bot.helpers.localization import get_text
from config import config

logger = logging.getLogger(__name__)


class Player:
    """Core music player functionality."""
    
    def __init__(self, calls: PyTgCalls):
        self.calls = calls
        self.playing_messages: Dict[int, Message] = {}
        self.progress_tasks: Dict[int, asyncio.Task] = {}
        self.is_playing: Dict[int, bool] = {}
        self.is_paused: Dict[int, bool] = {}
        
        # Register handlers
        self.calls.on_stream_end(self._on_stream_end)
    
    async def join(self, chat_id: int) -> bool:
        """Join voice chat."""
        try:
            await self.calls.join_group_call(
                chat_id,
                AudioPiped("input.mp3")  # Dummy file
            )
            return True
        except AlreadyJoinedError:
            return True
        except NoActiveGroupCall:
            logger.error(f"No active group call in {chat_id}")
            return False
        except Exception as e:
            logger.error(f"Failed to join {chat_id}: {e}")
            return False
    
    async def leave(self, chat_id: int) -> bool:
        """Leave voice chat."""
        try:
            await self.calls.leave_group_call(chat_id)
            
            # Cancel progress task
            if chat_id in self.progress_tasks:
                self.progress_tasks[chat_id].cancel()
                del self.progress_tasks[chat_id]
            
            # Clean state
            self.is_playing.pop(chat_id, None)
            self.is_paused.pop(chat_id, None)
            self.playing_messages.pop(chat_id, None)
            
            return True
        except Exception as e:
            logger.error(f"Failed to leave {chat_id}: {e}")
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
            
            # Build ffmpeg parameters for resuming
            additional_params = ""
            if resume_from > 0:
                additional_params = f"-ss {resume_from}"
            
            # Join if not already
            if chat_id not in self.is_playing:
                if not await self.join(chat_id):
                    return False
            
            # Stream the audio
            await self.calls.change_stream(
                chat_id,
                AudioPiped(
                    track.file_path,
                    additional_ffmpeg_parameters=additional_params
                )
            )
            
            self.is_playing[chat_id] = True
            self.is_paused[chat_id] = False
            
            # Start progress updater
            if chat_id in self.progress_tasks:
                self.progress_tasks[chat_id].cancel()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to play in {chat_id}: {e}")
            return False
    
    async def pause(self, chat_id: int) -> bool:
        """Pause playback."""
        try:
            await self.calls.pause_stream(chat_id)
            self.is_paused[chat_id] = True
            return True
        except Exception as e:
            logger.error(f"Failed to pause {chat_id}: {e}")
            return False
    
    async def resume(self, chat_id: int) -> bool:
        """Resume playback."""
        try:
            await self.calls.resume_stream(chat_id)
            self.is_paused[chat_id] = False
            return True
        except Exception as e:
            logger.error(f"Failed to resume {chat_id}: {e}")
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
            queue = queue_manager.get_queue(chat_id)
            queue.clear()
            
            await self.leave(chat_id)
            return True
        except Exception as e:
            logger.error(f"Failed to stop {chat_id}: {e}")
            return False
    
    async def _on_stream_end(self, chat_id: int, _) -> None:
        """Handle stream end event."""
        try:
            # Play next track
            await self.skip(chat_id)
        except Exception as e:
            logger.error(f"Error handling stream end: {e}")
    
    async def start_progress_updater(
        self,
        chat_id: int,
        message: Message,
        track: Track
    ) -> None:
        """Start progress bar updater task."""
        async def updater():
            elapsed = 0
            while chat_id in self.is_playing and self.is_playing[chat_id]:
                try:
                    if not self.is_paused.get(chat_id, False):
                        elapsed += config.PROGRESS_UPDATE_INTERVAL
                        
                        # Update message
                        progress_bar = formatting.progress_bar(
                            elapsed,
                            track.duration,
                            length=15
                        )
                        
                        text = get_text(
                            chat_id,
                            "now_playing",
                            title=track.title,
                            duration=formatting.duration(track.duration),
                            requester=track.requester_name,
                            progress_bar=progress_bar,
                            elapsed=formatting.duration(elapsed),
                            total=formatting.duration(track.duration)
                        )
                        
                        # Import keyboards here to avoid circular import
                        from bot.helpers.keyboards import keyboards
                        
                        await message.edit_text(
                            text,
                            reply_markup=keyboards.player_controls(
                                chat_id,
                                is_paused=self.is_paused.get(chat_id, False)
                            )
                        )
                    
                    await asyncio.sleep(config.PROGRESS_UPDATE_INTERVAL)
                    
                except Exception as e:
                    logger.error(f"Error updating progress: {e}")
                    break
        
        # Cancel existing task
        if chat_id in self.progress_tasks:
            self.progress_tasks[chat_id].cancel()
        
        # Start new task
        self.progress_tasks[chat_id] = asyncio.create_task(updater())
        self.playing_messages[chat_id] = message

# Global instance (will be initialized when clients are ready)
player: Optional[Player] = None
