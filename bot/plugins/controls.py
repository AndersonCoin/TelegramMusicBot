"""Playback control commands."""

from pyrogram import Client, filters
from pyrogram.types import Message
from bot.helpers.localization import get_text

@Client.on_message(filters.command("pause") & filters.group)
async def pause_command(client: Client, message: Message):
    """Handle /pause command."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Check if playing
    if chat_id not in client.music.player.active_chats:
        await message.reply(get_text(user_id, "not_playing"))
        return
    
    # Check admin
    member = await message.chat.get_member(user_id)
    if not member.privileges:
        await message.reply(get_text(user_id, "only_admins"))
        return
    
    # Pause
    if await client.music.player.pause(chat_id):
        await message.reply(get_text(user_id, "paused"))

@Client.on_message(filters.command("resume") & filters.group)
async def resume_command(client: Client, message: Message):
    """Handle /resume command."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Check if playing
    if chat_id not in client.music.player.active_chats:
        await message.reply(get_text(user_id, "not_playing"))
        return
    
    # Check admin
    member = await message.chat.get_member(user_id)
    if not member.privileges:
        await message.reply(get_text(user_id, "only_admins"))
        return
    
    # Resume
    if await client.music.player.resume(chat_id):
        await message.reply(get_text(user_id, "resumed"))

@Client.on_message(filters.command("skip") & filters.group)
async def skip_command(client: Client, message: Message):
    """Handle /skip command."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Check if playing
    if chat_id not in client.music.player.active_chats:
        await message.reply(get_text(user_id, "not_playing"))
        return
    
    # Check admin
    member = await message.chat.get_member(user_id)
    if not member.privileges:
        await message.reply(get_text(user_id, "only_admins"))
        return
    
    # Skip
    next_track = await client.music.player.skip(chat_id)
    if next_track:
        await message.reply(get_text(user_id, "skipped"))
    else:
        await message.reply(get_text(user_id, "stopped"))

@Client.on_message(filters.command("stop") & filters.group)
async def stop_command(client: Client, message: Message):
    """Handle /stop command."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Check if playing
    if chat_id not in client.music.player.active_chats:
        await message.reply(get_text(user_id, "not_playing"))
        return
    
    # Check admin
    member = await message.chat.get_member(user_id)
    if not member.privileges:
        await message.reply(get_text(user_id, "only_admins"))
        return
    
    # Stop
    if await client.music.player.stop(chat_id):
        await message.reply(get_text(user_id, "stopped"))
