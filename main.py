import os
import logging
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get environment variables
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Check variables
if not API_ID or not API_HASH or not BOT_TOKEN:
    logger.error("Missing environment variables!")
    exit(1)

# Create bot client
app = Client(
    "MusicBot",
    api_id=int(API_ID),
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

# Global variables
music_queue = {}
active_chats = set()

# Start command
@app.on_message(filters.command("start"))
async def start_command(client, message):
    user_name = message.from_user.first_name
    welcome_text = f"""
🎵 **Welcome {user_name}!**

I am a music bot for Telegram groups.

**Available Commands:**
/play [song name] - Play a song
/pause - Pause playback
/resume - Resume playback
/skip - Skip current song
/stop - Stop playback
/queue - Show queue
/help - Show help

Add me to your group and make me admin!
"""
    await message.reply_text(welcome_text)
    logger.info(f"User {message.from_user.id} started the bot")

# Help command
@app.on_message(filters.command("help"))
async def help_command(client, message):
    help_text = """
📚 **Command List:**

**Music Commands:**
/play [song] - Play a song
/pause - Pause playback
/resume - Resume playback
/skip - Skip song
/stop - Stop playback
/queue - Show queue

**General Commands:**
/start - Start bot
/help - Show help
/ping - Check bot status
/stats - Bot statistics
"""
    await message.reply_text(help_text)

# Ping command
@app.on_message(filters.command("ping"))
async def ping_command(client, message):
    import time
    start = time.time()
    msg = await message.reply_text("🏓 Pong!")
    end = time.time()
    latency = round((end - start) * 1000, 2)
    await msg.edit(f"🏓 **Pong!**\nLatency: {latency}ms")

# Stats command
@app.on_message(filters.command("stats"))
async def stats_command(client, message):
    total_chats = len(active_chats)
    total_queues = len(music_queue)
    stats_text = f"""
📊 **Bot Statistics:**

Active Chats: {total_chats}
Music Queues: {total_queues}
Status: ✅ Online
Version: 1.0.0
"""
    await message.reply_text(stats_text)

# Play command
@app.on_message(filters.command(["play", "p"]))
async def play_command(client, message):
    if len(message.command) < 2:
        return await message.reply_text("❌ Usage: /play [song name]")
    
    song_name = " ".join(message.command[1:])
    chat_id = message.chat.id
    active_chats.add(chat_id)
    
    msg = await message.reply_text(f"🔍 Searching for: {song_name}")
    await asyncio.sleep(1)
    
    if chat_id not in music_queue:
        music_queue[chat_id] = []
    
    music_queue[chat_id].append({
        'title': song_name,
        'requested_by': message.from_user.first_name
    })
    
    position = len(music_queue[chat_id])
    
    await msg.edit(
        f"✅ **Added to queue!**\n\n"
        f"Song: {song_name}\n"
        f"Requested by: {message.from_user.first_name}\n"
        f"Position: #{position}"
    )
    logger.info(f"Song added to queue in chat {chat_id}")

# Queue command
@app.on_message(filters.command("queue"))
async def queue_command(client, message):
    chat_id = message.chat.id
    
    if chat_id not in music_queue or not music_queue[chat_id]:
        return await message.reply_text("📭 Queue is empty")
    
    queue_text = "📋 **Current Queue:**\n\n"
    for i, song in enumerate(music_queue[chat_id], 1):
        queue_text += f"{i}. {song['title']}\n"
        queue_text += f"   By: {song['requested_by']}\n\n"
    
    await message.reply_text(queue_text)

# Stop command
@app.on_message(filters.command("stop"))
async def stop_command(client, message):
    chat_id = message.chat.id
    
    if chat_id in music_queue:
        music_queue[chat_id] = []
    
    if chat_id in active_chats:
        active_chats.remove(chat_id)
    
    await message.reply_text("⏹️ **Playback stopped**")
    logger.info(f"Stopped playback in chat {chat_id}")

# Pause command
@app.on_message(filters.command("pause"))
async def pause_command(client, message):
    await message.reply_text("⏸️ **Playback paused**")

# Resume command
@app.on_message(filters.command("resume"))
async def resume_command(client, message):
    await message.reply_text("▶️ **Playback resumed**")

# Skip command
@app.on_message(filters.command("skip"))
async def skip_command(client, message):
    chat_id = message.chat.id
    
    if chat_id in music_queue and music_queue[chat_id]:
        skipped = music_queue[chat_id].pop(0)
        await message.reply_text(f"⏭️ **Skipped:** {skipped['title']}")
    else:
        await message.reply_text("❌ No songs to skip")

# Test command
@app.on_message(filters.command("test"))
async def test_command(client, message):
    await message.reply_text("✅ **Bot is working perfectly!**")

# Main function
async def main():
    try:
        logger.info("Starting bot...")
        await app.start()
        
        me = await app.get_me()
        logger.info(f"Bot started! Username: @{me.username}")
        
        await idle()
        
        await app.stop()
        logger.info("Bot stopped")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        exit(1)

# Run the bot
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        
