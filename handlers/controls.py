from pyrogram import Client, filters
from pyrogram.types import Message
from py_tgcalls import StreamType
from utils.queue import get_queue, clear_queue, remove_from_queue

@Client.on_message(filters.command(["pause"]) & filters.group)
async def pause_command(client, message: Message):
    from main import pytgcalls
    
    chat_id = message.chat.id
    try:
        await pytgcalls.pause_stream(chat_id)
        await message.reply_text("⏸️ **Playback Paused**")
    except Exception as e:
        await message.reply_text(f"❌ **Error:** {str(e)}")

@Client.on_message(filters.command(["resume"]) & filters.group)
async def resume_command(client, message: Message):
    from main import pytgcalls
    
    chat_id = message.chat.id
    try:
        await pytgcalls.resume_stream(chat_id)
        await message.reply_text("▶️ **Playback Resumed**")
    except Exception as e:
        await message.reply_text(f"❌ **Error:** {str(e)}")

@Client.on_message(filters.command(["skip", "next"]) & filters.group)
async def skip_command(client, message: Message):
    from main import pytgcalls
    
    chat_id = message.chat.id
    queue = get_queue(chat_id)
    
    if not queue or len(queue) < 2:
        return await message.reply_text("❌ **No songs in queue to skip to!**")
    
    try:
        # Remove current song and play next
        remove_from_queue(chat_id, 0)
        next_song = queue[1]
        
        await pytgcalls.change_stream(
            chat_id,
            AudioPiped(next_song['url'])
        )
        
        await message.reply_text(
            f"⏭️ **Skipped! Now Playing:**\n"
            f"🎵 {next_song['title']}"
        )
    except Exception as e:
        await message.reply_text(f"❌ **Error:** {str(e)}")

@Client.on_message(filters.command(["stop", "end"]) & filters.group)
async def stop_command(client, message: Message):
    from main import pytgcalls
    
    chat_id = message.chat.id
    try:
        clear_queue(chat_id)
        await pytgcalls.leave_group_call(chat_id)
        await message.reply_text("⏹️ **Playback Stopped & Queue Cleared**")
    except Exception as e:
        await message.reply_text(f"❌ **Error:** {str(e)}")

@Client.on_message(filters.command(["volume", "vol"]) & filters.group)
async def volume_command(client, message: Message):
    from main import pytgcalls
    
    if len(message.command) < 2:
        return await message.reply_text("❌ **Usage:** /volume [1-100]")
    
    try:
        volume = int(message.command[1])
        if not 1 <= volume <= 100:
            return await message.reply_text("❌ **Volume must be between 1-100**")
        
        chat_id = message.chat.id
        await pytgcalls.change_volume_call(chat_id, volume)
        await message.reply_text(f"🔊 **Volume set to {volume}%**")
    except ValueError:
        await message.reply_text("❌ **Please provide a valid number**")
    except Exception as e:
        await message.reply_text(f"❌ **Error:** {str(e)}")
