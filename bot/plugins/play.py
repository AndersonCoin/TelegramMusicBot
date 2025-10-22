"""Play command and related functionality."""

import asyncio
import logging
import time
from typing import Dict

from pyrogram import Client, filters
from pyrogram.types import Message

from bot.core.queue import queue_manager, Track
from bot.helpers.assistant import assistant_manager
from bot.helpers.formatting import formatting
from bot.helpers.keyboards import keyboards
from bot.helpers.localization import get_text
from bot.helpers.youtube import youtube
from config import config

logger = logging.getLogger(__name__)

# Rate limiting
last_play_time: Dict[int, float] = {}


@Client.on_message(filters.command("play") & filters.group)
async def play_command(client: Client, message: Message):
    """Handle /play command."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Rate limiting
    current_time = time.time()
    if user_id in last_play_time:
        time_diff = current_time - last_play_time[user_id]
        if time_diff < config.RATE_LIMIT_SECONDS:
            await message.reply_text(
                get_text(
                    message.chat,
                    "rate_limited",
                    seconds=int(config.RATE_LIMIT_SECONDS - time_diff)
                )
            )
            return
    
    last_play_time[user_id] = current_time
    
    # Get query
    if len(message.command) < 2:
        await message.reply_text(get_text(message.chat, "invalid_url"))
        return
    
    query = " ".join(message.command[1:])
    
    # Ensure assistant is in chat
    if assistant_manager:
        if not await assistant_manager.ensure_in_chat(message.chat):
            await message.reply_text(get_text(message.chat, "error", message="Failed to add assistant"))
            return
    
    # Search
    search_msg = await message.reply_text(
        get_text(message.chat, "searching", query=query)
    )
    
    result = await youtube.search(query)
    if not result:
        await search_msg.edit_text(get_text(message.chat, "invalid_url"))
        return
    
    # Download
    await search_msg.edit_text(
        get_text(message.chat, "downloading", title=result["title"])
    )
    
    download = await youtube.download(result["url"])
    if not download or not download.get("file_path"):
        await search_msg.edit_text(
            get_text(message.chat, "download_error", error="Failed to download")
        )
        return
    
    # Add to queue
    track = Track(
        id=download["id"],
        title=download["title"],
        duration=download["duration"],
        url=download["url"],
        file_path=download["file_path"],
        thumbnail=download.get("thumbnail"),
        requested_by=user_id,
        requester_name=message.from_user.first_name
    )
    
    queue = queue_manager.get_queue(chat_id)
    position = queue.add(track)
    
    # Get player instance
    from bot.core import player
    
    if not player:
        logger.error("Player not initialized")
        await search_msg.edit_text(
            get_text(message.chat, "error", message="Player not initialized")
        )
        return
    
    # If not playing, start playback
    if not player.is_playing.get(chat_id):
        if await player.play(chat_id, track):
            # Create now playing message
            text = get_text(
                message.chat,
                "now_playing",
                title=track.title,
                duration=formatting.duration(track.duration),
                requester=track.requester_name,
                progress_bar=formatting.progress_bar(0, track.duration, 15),
                elapsed="00:00",
                total=formatting.duration(track.duration)
            )
            
            now_playing = await search_msg.edit_text(
                text,
                reply_markup=keyboards.player_controls(chat_id)
            )
            
            # Start progress updater
            await player.start_progress_updater(chat_id, now_playing, track)
        else:
            await search_msg.edit_text(
                get_text(message.chat, "error", message="Failed to start playback")
            )
    else:
        # Added to queue
        await search_msg.edit_text(
            get_text(
                message.chat,
                "added_to_queue",
                title=track.title,
                position=position
            )
        )
