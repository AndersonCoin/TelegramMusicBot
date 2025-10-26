import os
import logging
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pytgcalls import PyTgCalls, StreamType
from pytgcalls.types.input_stream import AudioPiped
from pytgcalls.exceptions import NoActiveGroupCall
from dotenv import load_dotenv
from aiohttp import web
import yt_dlp

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment variables
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
SESSION_STRING = os.getenv("SESSION_STRING")  # User bot session
PORT = int(os.getenv("PORT", 10000))

if not all([API_ID, API_HASH, BOT_TOKEN]):
    logger.error("Missing environment variables!")
    exit(1)

# Bot client
bot = Client(
    "MusicBot",
    api_id=int(API_ID),
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

# User client (for voice chat)
if SESSION_STRING:
    user = Client(
        "UserBot",
        api_id=int(API_ID),
        api_hash=API_HASH,
        session_string=SESSION_STRING,
        in_memory=True
    )
    calls = PyTgCalls(user)
    USERBOT_AVAILABLE = True
else:
    user = None
    calls = None
    USERBOT_AVAILABLE = False
    logger.warning("No SESSION_STRING found! Music playback will not work.")

# Global variables
music_queue = {}
active_chats = set()
currently_playing = {}

# YouTube downloader config
ydl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'geo_bypass': True,
}

# Helper function to download from YouTube
async def download_song(query):
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if query.startswith(('http://', 'https://')):
                info = ydl.extract_info(query, download=False)
            else:
                info = ydl.extract_info(f"ytsearch:{query}", download=False)
                if 'entries' in info:
                    info = info['entries'][0]
            
            return {
                'title': info.get('title', 'Unknown'),
                'url': info['url'],
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'webpage_url': info.get('webpage_url', '')
            }
    except Exception as e:
        logger.error(f"Error downloading: {e}")
        return None

# Format duration
def format_duration(seconds):
    if not seconds:
        return "Live"
    mins, secs = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"

# Play next song in queue
async def play_next(chat_id):
    if chat_id not in music_queue or not music_queue[chat_id]:
        try:
            await calls.leave_group_call(chat_id)
            if chat_id in currently_playing:
                del currently_playing[chat_id]
            logger.info(f"Queue empty, left chat {chat_id}")
        except Exception as e:
            logger.error(f"Error leaving call: {e}")
        return
    
    next_song = music_queue[chat_id].pop(0)
    try:
        await calls.play(
            chat_id,
            AudioPiped(next_song['url']),
            stream_type=StreamType().pulse_stream
        )
        currently_playing[chat_id] = next_song
        logger.info(f"Now playing: {next_song['title']}")
    except Exception as e:
        logger.error(f"Error playing song: {e}")
        await play_next(chat_id)

# Bot commands
@bot.on_message(filters.command("start"))
async def start_command(client, message):
    status = "✅ Available" if USERBOT_AVAILABLE else "❌ Not Available"
    welcome_text = f"""
🎵 **Welcome to Music Bot!**

**Bot Status:** ✅ Online
**Music Playback:** {status}

**Available Commands:**
/play [song name] - Play a song
/pause - Pause playback
/resume - Resume playback
/skip - Skip current song
/stop - Stop and clear queue
/queue - Show current queue
/current - Show current song

Add me to your group and start a voice chat!
"""
    await message.reply_text(welcome_text)

@bot.on_message(filters.command("help"))
async def help_command(client, message):
    help_text = """
📚 **Command List:**

**Music Commands:**
/play [song/link] - Play a song
/pause - Pause playback
/resume - Resume playback
/skip - Skip current song
/stop - Stop playback
/queue - Show queue
/current - Current song

**Requirements:**
• Add bot to your group
• Make bot admin
• Start a voice chat
• Use /play command
"""
    await message.reply_text(help_text)

@bot.on_message(filters.command("ping"))
async def ping_command(client, message):
    import time
    start = time.time()
    msg = await message.reply_text("🏓 Pong!")
    end = time.time()
    latency = round((end - start) * 1000, 2)
    
    userbot_status = "✅ Online" if USERBOT_AVAILABLE else "❌ Offline"
    
    await msg.edit(
        f"🏓 **Pong!**\n"
        f"⚡ Latency: `{latency}ms`\n"
        f"🤖 Bot: ✅ Online\n"
        f"👤 UserBot: {userbot_status}"
    )

@bot.on_message(filters.command(["play", "p"]) & filters.group)
async def play_command(client, message):
    if not USERBOT_AVAILABLE:
        return await message.reply_text(
            "❌ **Music playback unavailable!**\n"
            "The assistant account is not configured."
        )
    
    if len(message.command) < 2:
        return await message.reply_text("❌ Usage: /play [song name or YouTube link]")
    
    query = " ".join(message.command[1:])
    chat_id = message.chat.id
    
    msg = await message.reply_text("🔍 **Searching...**")
    
    # Download song info
    song_info = await download_song(query)
    
    if not song_info:
        return await msg.edit("❌ **Song not found!**")
    
    # Add to queue
    if chat_id not in music_queue:
        music_queue[chat_id] = []
    
    music_queue[chat_id].append(song_info)
    position = len(music_queue[chat_id])
    
    # If nothing is playing, start playback
    if chat_id not in currently_playing:
        await msg.edit("🎵 **Starting playback...**")
        await play_next(chat_id)
        await msg.edit(
            f"▶️ **Now Playing:**\n\n"
            f"🎵 **{song_info['title']}**\n"
            f"⏱️ Duration: {format_duration(song_info['duration'])}\n"
            f"🔗 [YouTube Link]({song_info['webpage_url']})"
        )
    else:
        await msg.edit(
            f"✅ **Added to queue at position #{position}**\n\n"
            f"🎵 {song_info['title']}\n"
            f"⏱️ {format_duration(song_info['duration'])}"
        )

@bot.on_message(filters.command("pause") & filters.group)
async def pause_command(client, message):
    if not USERBOT_AVAILABLE:
        return await message.reply_text("❌ UserBot not available")
    
    chat_id = message.chat.id
    try:
        await calls.pause_stream(chat_id)
        await message.reply_text("⏸️ **Playback paused**")
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

@bot.on_message(filters.command("resume") & filters.group)
async def resume_command(client, message):
    if not USERBOT_AVAILABLE:
        return await message.reply_text("❌ UserBot not available")
    
    chat_id = message.chat.id
    try:
        await calls.resume_stream(chat_id)
        await message.reply_text("▶️ **Playback resumed**")
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

@bot.on_message(filters.command("skip") & filters.group)
async def skip_command(client, message):
    if not USERBOT_AVAILABLE:
        return await message.reply_text("❌ UserBot not available")
    
    chat_id = message.chat.id
    await message.reply_text("⏭️ **Skipping...**")
    await play_next(chat_id)

@bot.on_message(filters.command("stop") & filters.group)
async def stop_command(client, message):
    if not USERBOT_AVAILABLE:
        return await message.reply_text("❌ UserBot not available")
    
    chat_id = message.chat.id
    
    try:
        await calls.leave_group_call(chat_id)
        music_queue[chat_id] = []
        if chat_id in currently_playing:
            del currently_playing[chat_id]
        await message.reply_text("⏹️ **Stopped and cleared queue**")
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

@bot.on_message(filters.command("queue") & filters.group)
async def queue_command(client, message):
    chat_id = message.chat.id
    
    if chat_id not in music_queue or not music_queue[chat_id]:
        return await message.reply_text("📭 **Queue is empty**")
    
    queue_text = "📋 **Current Queue:**\n\n"
    
    if chat_id in currently_playing:
        queue_text += f"▶️ **Now Playing:**\n{currently_playing[chat_id]['title']}\n\n"
    
    queue_text += "**Up Next:**\n"
    for i, song in enumerate(music_queue[chat_id], 1):
        queue_text += f"{i}. {song['title']}\n"
    
    await message.reply_text(queue_text)

@bot.on_message(filters.command("current") & filters.group)
async def current_command(client, message):
    chat_id = message.chat.id
    
    if chat_id not in currently_playing:
        return await message.reply_text("❌ **Nothing is playing**")
    
    song = currently_playing[chat_id]
    await message.reply_text(
        f"▶️ **Now Playing:**\n\n"
        f"🎵 {song['title']}\n"
        f"⏱️ {format_duration(song['duration'])}\n"
        f"🔗 [YouTube Link]({song['webpage_url']})"
    )

# Web server
async def health_check(request):
    return web.Response(text="Bot is running! ✅")

async def index(request):
    bot_info = await bot.get_me()
    userbot_status = "Online" if USERBOT_AVAILABLE else "Offline"
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Music Bot Status</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }}
            .container {{
                text-align: center;
                background: rgba(255,255,255,0.1);
                padding: 40px;
                border-radius: 20px;
                backdrop-filter: blur(10px);
            }}
            h1 {{ margin: 0; font-size: 3em; }}
            .status {{ color: #4ade80; font-size: 1.5em; margin: 20px 0; }}
            .info {{ margin: 10px 0; font-size: 1.2em; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎵 Music Bot</h1>
            <div class="status">✅ Online</div>
            <div class="info">Bot: @{bot_info.username}</div>
            <div class="info">UserBot: {userbot_status}</div>
            <div class="info">Active Chats: {len(active_chats)}</div>
        </div>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')

async def start_web_server():
    app_web = web.Application()
    app_web.router.add_get('/', index)
    app_web.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app_web)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"Web server started on port {PORT}")

# Main function
async def main():
    try:
        logger.info("Starting bot...")
        
        # Start web server
        await start_web_server()
        
        # Start bot
        await bot.start()
        bot_info = await bot.get_me()
        logger.info(f"✅ Bot started: @{bot_info.username}")
        
        # Start user bot if available
        if USERBOT_AVAILABLE:
            await user.start()
            await calls.start()
            user_info = await user.get_me()
            logger.info(f"✅ UserBot started: {user_info.first_name}")
        else:
            logger.warning("⚠️ UserBot not available - music playback disabled")
        
        await idle()
        
        # Stop
        await bot.stop()
        if USERBOT_AVAILABLE:
            await calls.stop()
            await user.stop()
        
        logger.info("Bot stopped")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
