"""Play command and related functionality."""

import asyncio
import time
from pyrogram import Client, filters
from pyrogram.types import Message
from bot.core.queue import queue_manager, Track
from bot.helpers.youtube import YouTubeDownloader
from bot.helpers.localization import get_text
from bot.helpers.keyboards import Keyboards
from bot.helpers.formatting import format_duration, create_progress_bar
from bot.helpers.assistant import AssistantManager

# Rate limiting
user_last_play: dict[int, float] = {}

@Client.on_message(filters.command("play") & filters.group)
async def play_command(client: Client, message: Message):
    """Handle /play command."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Rate limiting
    last_play = user_last_play.get(user_id, 0)
    if time.time() - last_play < 3:
        await message.reply(
            get_text(user_id, "rate_limited", seconds=3)
        )
        return
    user_last_play[user_id] = time.time()
    
    # Get query
    if len(message.command) < 2:
        await message.reply(get_text(user_id, "error_occurred", error="No query provided"))
        return
    
    query = " ".join(message.command[1:])
    
    # Search message
    status_msg = await message.reply(
        get_text(user_id, "searching", query=query)
    )
    
    # Ensure assistant is ready
    ready, msg = await AssistantManager.ensure_in_chat(client.music, chat_id)
    if not ready:
        await status_msg.edit(get_text(user_id, "error_occurred", error=msg))
        return
    
    # Search or get info
    if query.startswith(("http://", "https://")):
        info = await YouTubeDownloader.get_info(query)
    else:
        info = await YouTubeDownloader.search(query)
    
    if not info:
        await status_msg.edit(get_text(user_id, "no_results", query=query))
        return
    
    # Extract info
    video_info = YouTubeDownloader.extract_info(info)
    
    # Update status
    await status_msg.edit(
        get_text(user_id, "downloading", title=video_info["title"])
    )
    
    # Download
    file_path, _ = await YouTubeDownloader.download(video_info["url"])
    if not file_path:
        await status_msg.edit(get_text(user_id, "error_occurred", error="Download failed"))
        return
    
    # Create track
    track = Track(
        url=video_info["url"],
        title=video_info["title"],
        duration=video_info["duration"],
        requester_id=user_id,
        requester_name=message.from_user.first_name,
        file_path=file_path,
        thumbnail=video_info.get("thumbnail")
    )
    
    # Add to queue
    queue = queue_manager.get_queue(chat_id)
    position = queue.add(track)
    
    # If first track, play immediately
    if position == 1:
        queue.current_index = 0
        
        # Join voice chat if needed
        if chat_id not in client.music.player.active_chats:
            await client.music.player.join(chat_id)
        
        # Play track
        await client.music.player.play(chat_id, track)
        
        # Create now playing message
        text = get_text(
            user_id,
            "now_playing",
            title=track.title,
            duration=format_duration(track.duration),
            requester=track.requester_name,
            progress_bar=create_progress_bar(0, track.duration),
            elapsed=format_duration(0),
            total=format_duration(track.duration)
        )
        
        now_playing = await status_msg.edit(
            text,
            reply_markup=Keyboards.player_controls(chat_id)
        )
        
        # Start progress updater
        await client.music.player.start_progress_updater(chat_id, now_playing.id)
        
    else:
        # Added to queue
        await status_msg.edit(
            get_text(user_id, "added_to_queue", position=position)
        )
