"""Playback control commands."""

from pyrogram import Client, filters
from pyrogram.types import Message

from bot.core.player import player
from bot.core.queue import queue_manager
from bot.helpers.localization import get_text


@Client.on_message(filters.command("pause") & filters.group)
async def pause_command(client: Client, message: Message):
    """Handle /pause command."""
    chat_id = message.chat.id
    
    # Check admin
    member = await message.chat.get_member(message.from_user.id)
    if not member.privileges:
        await message.reply_text(get_text(message.chat, "admin_only"))
        return
    
    if not player or not player.is_playing.get(chat_id):
        await message.reply_text(get_text(message.chat, "not_in_call"))
        return
    
    if await player.pause(chat_id):
        await message.reply_text(get_text(message.chat, "paused"))
    else:
        await message.reply_text(get_text(message.chat, "error", message="Failed to pause"))


@Client.on_message(filters.command("resume") & filters.group)
async def resume_command(client: Client, message: Message):
    """Handle /resume command."""
    chat_id = message.chat.id
    
    # Check admin
    member = await message.chat.get_member(message.from_user.id)
    if not member.privileges:
        await message.reply_text(get_text(message.chat, "admin_only"))
        return
    
    if not player or not player.is_playing.get(chat_id):
        # Try to resume from saved state
        from bot.persistence.state import StateManager
        state_mgr = StateManager()
        state = await state_mgr.get_state(chat_id)
        
        if state:
            await message.reply_text(
                get_text(message.chat, "resuming_from", position=state.position)
            )
            # Resume logic here
        else:
            await message.reply_text(get_text(message.chat, "nothing_to_resume"))
        return
    
    if await player.resume(chat_id):
        await message.reply_text(get_text(message.chat, "resumed"))
    else:
        await message.reply_text(get_text(message.chat, "error", message="Failed to resume"))


@Client.on_message(filters.command("skip") & filters.group)
async def skip_command(client: Client, message: Message):
    """Handle /skip command."""
    chat_id = message.chat.id
    
    # Check admin
    member = await message.chat.get_member(message.from_user.id)
    if not member.privileges:
        await message.reply_text(get_text(message.chat, "admin_only"))
        return
    
    if not player or not player.is_playing.get(chat_id):
        await message.reply_text(get_text(message.chat, "not_in_call"))
        return
    
    next_track = await player.skip(chat_id)
    if next_track:
        await message.reply_text(get_text(message.chat, "skipped"))
    else:
        await message.reply_text(get_text(message.chat, "queue_empty"))


@Client.on_message(filters.command("stop") & filters.group)
async def stop_command(client: Client, message: Message):
    """Handle /stop command."""
    chat_id = message.chat.id
    
    # Check admin
    member = await message.chat.get_member(message.from_user.id)
    if not member.privileges:
        await message.reply_text(get_text(message.chat, "admin_only"))
        return
    
    if not player or not player.is_playing.get(chat_id):
        await message.reply_text(get_text(message.chat, "not_in_call"))
        return
    
    if await player.stop(chat_id):
        await message.reply_text(get_text(message.chat, "stopped"))
        
        # Clear saved state
        from bot.persistence.state import StateManager
        state_mgr = StateManager()
        await state_mgr.delete_state(chat_id)
    else:
        await message.reply_text(get_text(message.chat, "error", message="Failed to stop"))
