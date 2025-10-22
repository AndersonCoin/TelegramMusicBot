"""Music player core functionality."""

import asyncio
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from pytgcalls import StreamType
from pytgcalls.types import AudioPiped, MediaStream
from pytgcalls.types.stream import StreamAudioEnded
from bot.core.queue import queue_manager, Track
from bot.helpers.formatting import format_duration
from bot.persistence.state import PlaybackState

logger = logging.getLogger(__name__)

class Player:
    """Main player controller."""
    
    def __init__(self, client):
        self.client = client
        self.pytgcalls = client.pytgcalls
        self.active_chats: Dict[int, Dict[str, Any]] = {}
        self.progress_tasks: Dict[int, asyncio.Task] = {}
        self.state_tasks: Dict[int, asyncio.Task] = {}
        
        # Register handlers
        self.pytgcalls.on_stream_end(self.on_stream_end)
        
    async def join(self, chat_id: int) -> bool:
        """Join voice chat."""
        try:
            await self.pytgcalls.join_group_call(
                chat_id,
                MediaStream(
                    audio=AudioPiped("input.raw"),
                    video=None
                ),
                stream_type=StreamType().live_stream
            )
            return True
        except Exception as e:
            logger.error(f"Failed to join {chat_id}: {e}")
            return False
    
    async def leave(self, chat_id: int) -> bool:
        """Leave voice chat."""
        try:
            await self.pytgcalls.leave_group_call(chat_id)
            self._cleanup_chat(chat_id)
            return True
        except Exception as e:
            logger.error(f"Failed to leave {chat_id}: {e}")
            return False
    
    async def play(self, chat_id: int, track: Track, resume_from: int = 0) -> bool:
        """Play a track."""
        try:
            # Prepare ffmpeg parameters for resume
            ffmpeg_params = []
            if resume_from > 0:
                ffmpeg_params.extend(["-ss", str(resume_from)])
            
            # Create audio stream
            audio = AudioPiped(
                track.file_path,
                additional_ffmpeg_parameters=" ".join(ffmpeg_params) if ffmpeg_params else None
            )
            
            # Change or start stream
            if chat_id in self.active_chats:
                await self.pytgcalls.change_stream(chat_id, audio)
            else:
                await self.pytgcalls.play(chat_id, audio)
            
            # Update active chat info
            self.active_chats[chat_id] = {
                "track": track,
                "paused": False,
                "position": resume_from,
                "message_id": None
            }
            
            # Start state saver
            await self._start_state_saver(chat_id)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to play in {chat_id}: {e}")
            return False
    
    async def pause(self, chat_id: int) -> bool:
        """Pause playback."""
        try:
            await self.pytgcalls.pause_stream(chat_id)
            if chat_id in self.active_chats:
                self.active_chats[chat_id]["paused"] = True
            return True
        except Exception as e:
            logger.error(f"Failed to pause {chat_id}: {e}")
            return False
    
    async def resume(self, chat_id: int) -> bool:
        """Resume playback."""
        try:
            await self.pytgcalls.resume_stream(chat_id)
            if chat_id in self.active_chats:
                self.active_chats[chat_id]["paused"] = False
            return True
        except Exception as e:
            logger.error(f"Failed to resume {chat_id}: {e}")
            return False
    
    async def stop(self, chat_id: int) -> bool:
        """Stop playback and clear queue."""
        try:
            await self.pytgcalls.leave_group_call(chat_id)
            queue_manager.get_queue(chat_id).clear()
            self._cleanup_chat(chat_id)
            await self.client.state_manager.remove_state(chat_id)
            return True
        except Exception as e:
            logger.error(f"Failed to stop {chat_id}: {e}")
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
    
    async def on_stream_end(self, client, update: StreamAudioEnded):
        """Handle stream end event."""
        chat_id = update.chat_id
        await self.skip(chat_id)
    
    def _cleanup_chat(self, chat_id: int):
        """Clean up chat resources."""
        # Cancel tasks
        if chat_id in self.progress_tasks:
            self.progress_tasks[chat_id].cancel()
            del self.progress_tasks[chat_id]
        
        if chat_id in self.state_tasks:
            self.state_tasks[chat_id].cancel()
            del self.state_tasks[chat_id]
        
        # Remove from active
        self.active_chats.pop(chat_id, None)
    
    async def _start_state_saver(self, chat_id: int):
        """Start periodic state saving."""
        # Cancel existing task
        if chat_id in self.state_tasks:
            self.state_tasks[chat_id].cancel()
        
        # Start new task
        async def save_state():
            while True:
                await asyncio.sleep(15)
                if chat_id in self.active_chats:
                    info = self.active_chats[chat_id]
                    state = PlaybackState(
                        chat_id=chat_id,
                        track_path=info["track"].file_path,
                        position=info["position"] + 15,  # Approximate
                        track_data=info["track"].__dict__
                    )
                    await self.client.state_manager.save_state(state)
        
        self.state_tasks[chat_id] = asyncio.create_task(save_state())
    
    async def start_progress_updater(self, chat_id: int, message_id: int):
        """Start progress bar updater for now playing message."""
        if chat_id in self.progress_tasks:
            self.progress_tasks[chat_id].cancel()
        
        if chat_id in self.active_chats:
            self.active_chats[chat_id]["message_id"] = message_id
        
        async def update_progress():
            elapsed = 0
            while True:
                await asyncio.sleep(10)
                if chat_id not in self.active_chats:
                    break
                    
                info = self.active_chats[chat_id]
                if info["paused"]:
                    continue
                    
                elapsed += 10
                info["position"] += 10
                
                # Update message (implement in play.py)
                # This will be called from the plugin
        
        self.progress_tasks[chat_id] = asyncio.create_task(update_progress())
    
    async def resume_all_playbacks(self):
        """Resume all saved playbacks on startup."""
        states = await self.client.state_manager.get_all_states()
        
        for state in states:
            try:
                # Recreate track
                track = Track(
                    url=state.track_data.get("url", ""),
                    title=state.track_data.get("title", "Unknown"),
                    duration=state.track_data.get("duration", 0),
                    requester_id=state.track_data.get("requester_id", 0),
                    requester_name=state.track_data.get("requester_name", "Unknown"),
                    file_path=state.track_path
                )
                
                # Check if file exists
                if not Path(state.track_path).exists():
                    continue
                
                # Join and play
                await self.join(state.chat_id)
                await self.play(state.chat_id, track, resume_from=state.position)
                
                # Notify chat
                try:
                    from bot.helpers.localization import get_text
                    text = get_text(state.chat_id, "resuming_playback")
                    await self.client.bot.send_message(state.chat_id, text)
                except:
                    pass
                    
            except Exception as e:
                logger.error(f"Failed to resume playback in {state.chat_id}: {e}")
    
    async def stop_all(self):
        """Stop all active playbacks."""
        for chat_id in list(self.active_chats.keys()):
            await self.stop(chat_id)
