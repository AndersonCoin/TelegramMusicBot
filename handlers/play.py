from pyrogram import Client, filters
from pyrogram.types import Message
from py_tgcalls import StreamType
from py_tgcalls.types.input_stream import AudioPiped
from utils.youtube import download_song
from utils.queue import add_to_queue, get_queue
import asyncio

@Client.on_message(filters.command(["play", "p"]) & filters.group)
async def play_command(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("❌ **Usage:** /play [song name or youtube link]")
    
    query = " ".join(message.command[1:])
    chat_id = message.chat.id
    
    # Send searching message
    msg = await message.reply_text("🔍 **Searching...**")
    
    try:
        # Download song
        song_info = await download_song(query)
        
        if not song_info:
            return await msg.edit("❌ **Song not found!**")
        
        # Add to queue
        position = add_to_queue(chat_id, song_info)
        
        # If not playing, start playback
        if position == 1:
            await start_playback(chat_id, song_info)
            await msg.edit(
                f"▶️ **Now Playing:**\n"
                f"🎵 {song_info['title']}\n"
                f"👤 {song_info['uploader']}\n"
                f"⏱️ {song_info['duration']}"
            )
        else:
            await msg.edit(
                f"#️⃣ **Added to Queue at position {position}**\n"
                f"🎵 {song_info['title']}"
            )
            
    except Exception as e:
        await msg.edit(f"❌ **Error:** {str(e)}")

async def start_playback(chat_id, song_info):
    from main import pytgcalls
    
    await pytgcalls.join_group_call(
        chat_id,
        AudioPiped(song_info['url']),
        stream_type=StreamType().pulse_stream,
    )
