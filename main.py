import os
import logging
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from aiohttp import web
import yt_dlp
from typing import Dict, List

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
SESSION_STRING = os.getenv("SESSION_STRING")
PORT = int(os.getenv("PORT", 10000))

if not all([API_ID, API_HASH, BOT_TOKEN]):
    logger.error("Missing required variables!")
    exit(1)

# Bot
bot = Client(
    "MusicBot",
    api_id=int(API_ID),
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

# UserBot
userbot_available = False
if SESSION_STRING:
    try:
        userbot = Client(
            "UserBot",
            api_id=int(API_ID),
            api_hash=API_HASH,
            session_string=SESSION_STRING,
            in_memory=True
        )
        userbot_available = True
        logger.info("✅ UserBot configured")
    except Exception as e:
        logger.error(f"UserBot error: {e}")
        userbot = None
else:
    userbot = None
    logger.warning("⚠️ No SESSION_STRING")

# PyTgCalls with correct imports for v2.x
pytgcalls_available = False
calls = None

if userbot_available:
    try:
        from pytgcalls import PyTgCalls
        from pytgcalls.types import MediaStream, AudioQuality
        
        calls = PyTgCalls(userbot)
        pytgcalls_available = True
        logger.info("✅ PyTgCalls imported successfully")
    except ImportError as e:
        logger.warning(f"⚠️ PyTgCalls import failed: {e}")
        logger.warning("Music playback will be limited")
    except Exception as e:
        logger.error(f"PyTgCalls error: {e}")

# Global data
music_queue: Dict[int, List[Dict]] = {}
currently_playing: Dict[int, Dict] = {}

# YouTube config
ydl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'geo_bypass': True,
    'nocheckcertificate': True,
}

# Download from YouTube
async def download_song(query: str):
    try:
        loop = asyncio.get_event_loop()
        
        def extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if query.startswith(('http://', 'https://')):
                    info = ydl.extract_info(query, download=False)
                else:
                    info = ydl.extract_info(f"ytsearch:{query}", download=False)
                    if 'entries' in info and info['entries']:
                        info = info['entries'][0]
                return info
        
        info = await loop.run_in_executor(None, extract)
        
        if not info:
            return None
        
        return {
            'title': info.get('title', 'Unknown'),
            'url': info.get('url'),
            'duration': info.get('duration', 0),
            'thumbnail': info.get('thumbnail', ''),
            'webpage_url': info.get('webpage_url', ''),
            'uploader': info.get('uploader', 'Unknown')
        }
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None

# Format duration
def format_duration(seconds):
    if not seconds:
        return "Live"
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d}" if hours else f"{mins:02d}:{secs:02d}"

# Play next song
async def play_next_song(chat_id: int):
    if not pytgcalls_available or not calls:
        return
    
    if chat_id not in music_queue or not music_queue[chat_id]:
        try:
            await calls.leave_call(chat_id)
            if chat_id in currently_playing:
                del currently_playing[chat_id]
            logger.info(f"Queue empty, left {chat_id}")
        except:
            pass
        return
    
    next_song = music_queue[chat_id].pop(0)
    
    try:
        # Using correct py-tgcalls 2.x API
        await calls.play(
            chat_id,
            MediaStream(
                next_song['url'],
                audio_parameters=AudioQuality.HIGH
            )
        )
        currently_playing[chat_id] = next_song
        logger.info(f"▶️ Playing: {next_song['title']}")
    except Exception as e:
        logger.error(f"Play error: {e}")
        await play_next_song(chat_id)

# Stream ended handler
if pytgcalls_available and calls:
    @calls.on_stream_end()
    async def on_stream_end(client, update):
        try:
            chat_id = update.chat_id
            logger.info(f"Stream ended in {chat_id}")
            await play_next_song(chat_id)
        except Exception as e:
            logger.error(f"Stream end handler error: {e}")

# Commands
@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    status = "✅ Available" if (userbot_available and pytgcalls_available) else "❌ Not Available"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add to Group", 
            url=f"https://t.me/{(await client.get_me()).username}?startgroup=true")],
        [InlineKeyboardButton("📚 Help", callback_data="help"),
         InlineKeyboardButton("ℹ️ About", callback_data="about")]
    ])
    
    await message.reply_text(
        f"🎵 **Welcome to Music Bot!**\n\n"
        f"**Status:**\n"
        f"🤖 Bot: ✅ Online\n"
        f"🎶 Music: {status}\n\n"
        f"**Quick Start:**\n"
        f"1. Add me to your group\n"
        f"2. Make me admin\n"
        f"3. Start voice chat\n"
        f"4. Use /play [song name]\n\n"
        f"Type /help for all commands!",
        reply_markup=keyboard
    )

@bot.on_message(filters.command("help"))
async def help_cmd(client, message):
    await message.reply_text(
        "📚 **Music Bot Commands**\n\n"
        "**🎵 Music:**\n"
        "• /play [song] - Play a song\n"
        "• /pause - Pause playback\n"
        "• /resume - Resume playback\n"
        "• /skip - Skip current song\n"
        "• /stop - Stop & clear queue\n"
        "• /queue - Show queue\n"
        "• /current - Current song\n\n"
        "**ℹ️ Info:**\n"
        "• /ping - Check status\n"
        "• /stats - Statistics"
    )

@bot.on_message(filters.command("ping"))
async def ping_cmd(client, message):
    import time
    start = time.time()
    msg = await message.reply_text("🏓 Pinging...")
    end = time.time()
    latency = round((end - start) * 1000, 2)
    
    userbot_status = "✅" if userbot_available else "❌"
    calls_status = "✅" if pytgcalls_available else "❌"
    
    await msg.edit(
        f"🏓 **Pong!**\n\n"
        f"⚡ **Latency:** `{latency}ms`\n"
        f"🤖 **Bot:** ✅ Online\n"
        f"👤 **UserBot:** {userbot_status}\n"
        f"🎵 **PyTgCalls:** {calls_status}\n"
        f"💬 **Active:** {len(currently_playing)}"
    )

@bot.on_message(filters.command("stats"))
async def stats_cmd(client, message):
    await message.reply_text(
        f"📊 **Statistics**\n\n"
        f"💬 **Chats:** {len(music_queue)}\n"
        f"▶️ **Playing:** {len(currently_playing)}\n"
        f"📋 **Queued:** {sum(len(q) for q in music_queue.values())}\n"
        f"✅ **Status:** Online"
    )

@bot.on_message(filters.command(["play", "p"]) & filters.group)
async def play_cmd(client, message):
    if not userbot_available or not pytgcalls_available:
        return await message.reply_text(
            "❌ **Music playback unavailable!**\n\n"
            "UserBot or PyTgCalls not configured.\n"
            "Contact bot owner."
        )
    
    if len(message.command) < 2:
        return await message.reply_text(
            "❌ **Usage:**\n"
            "`/play [song name or YouTube link]`\n\n"
            "**Example:**\n"
            "`/play Believer Imagine Dragons`"
        )
    
    query = " ".join(message.command[1:])
    chat_id = message.chat.id
    
    msg = await message.reply_text("🔍 **Searching...**")
    
    song_info = await download_song(query)
    
    if not song_info:
        return await msg.edit("❌ **Song not found!**")
    
    if chat_id not in music_queue:
        music_queue[chat_id] = []
    
    music_queue[chat_id].append(song_info)
    position = len(music_queue[chat_id])
    
    if chat_id not in currently_playing:
        await msg.edit("🎵 **Joining voice chat...**")
        try:
            await play_next_song(chat_id)
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⏸️ Pause", callback_data=f"pause_{chat_id}"),
                 InlineKeyboardButton("⏭️ Skip", callback_data=f"skip_{chat_id}")],
                [InlineKeyboardButton("⏹️ Stop", callback_data=f"stop_{chat_id}")]
            ])
            
            await msg.edit(
                f"▶️ **Now Playing:**\n\n"
                f"🎵 {song_info['title']}\n"
                f"👤 {song_info['uploader']}\n"
                f"⏱️ {format_duration(song_info['duration'])}\n"
                f"🔗 [Link]({song_info['webpage_url']})\n\n"
                f"Requested by: {message.from_user.mention}",
                reply_markup=keyboard,
                disable_web_page_preview=False
            )
        except Exception as e:
            if "No active group call" in str(e) or "GROUP_CALL_INVALID" in str(e):
                await msg.edit(
                    "❌ **No active voice chat!**\n\n"
                    "Please start a voice chat first."
                )
            else:
                await msg.edit(f"❌ **Error:** {str(e)}")
            logger.error(f"Play error: {e}")
    else:
        await msg.edit(
            f"✅ **Added to queue #{position}**\n\n"
            f"🎵 {song_info['title']}\n"
            f"⏱️ {format_duration(song_info['duration'])}"
        )

@bot.on_message(filters.command("pause") & filters.group)
async def pause_cmd(client, message):
    if not pytgcalls_available:
        return await message.reply_text("❌ Not available")
    
    try:
        await calls.pause_stream(message.chat.id)
        await message.reply_text("⏸️ **Paused**")
    except Exception as e:
        await message.reply_text(f"❌ {str(e)}")

@bot.on_message(filters.command("resume") & filters.group)
async def resume_cmd(client, message):
    if not pytgcalls_available:
        return await message.reply_text("❌ Not available")
    
    try:
        await calls.resume_stream(message.chat.id)
        await message.reply_text("▶️ **Resumed**")
    except Exception as e:
        await message.reply_text(f"❌ {str(e)}")

@bot.on_message(filters.command("skip") & filters.group)
async def skip_cmd(client, message):
    if not pytgcalls_available:
        return await message.reply_text("❌ Not available")
    
    chat_id = message.chat.id
    
    if chat_id not in currently_playing:
        return await message.reply_text("❌ Nothing playing")
    
    await message.reply_text("⏭️ **Skipping...**")
    await play_next_song(chat_id)

@bot.on_message(filters.command("stop") & filters.group)
async def stop_cmd(client, message):
    if not pytgcalls_available:
        return await message.reply_text("❌ Not available")
    
    chat_id = message.chat.id
    
    try:
        await calls.leave_call(chat_id)
        
        if chat_id in music_queue:
            music_queue[chat_id] = []
        if chat_id in currently_playing:
            del currently_playing[chat_id]
        
        await message.reply_text("⏹️ **Stopped**")
    except Exception as e:
        await message.reply_text(f"❌ {str(e)}")

@bot.on_message(filters.command("queue") & filters.group)
async def queue_cmd(client, message):
    chat_id = message.chat.id
    
    if chat_id not in currently_playing and (chat_id not in music_queue or not music_queue[chat_id]):
        return await message.reply_text("📭 **Queue empty**")
    
    text = "📋 **Queue:**\n\n"
    
    if chat_id in currently_playing:
        current = currently_playing[chat_id]
        text += f"▶️ **Now:** {current['title']}\n\n"
    
    if chat_id in music_queue and music_queue[chat_id]:
        text += "**Next:**\n"
        for i, song in enumerate(music_queue[chat_id][:10], 1):
            text += f"{i}. {song['title']}\n"
        
        if len(music_queue[chat_id]) > 10:
            text += f"\n_...{len(music_queue[chat_id]) - 10} more_"
    
    await message.reply_text(text)

@bot.on_message(filters.command("current") & filters.group)
async def current_cmd(client, message):
    chat_id = message.chat.id
    
    if chat_id not in currently_playing:
        return await message.reply_text("❌ Nothing playing")
    
    song = currently_playing[chat_id]
    await message.reply_text(
        f"▶️ **Now Playing:**\n\n"
        f"🎵 {song['title']}\n"
        f"👤 {song['uploader']}\n"
        f"⏱️ {format_duration(song['duration'])}\n"
        f"🔗 [Link]({song['webpage_url']})",
        disable_web_page_preview=False
    )

# Callbacks
@bot.on_callback_query()
async def callback_handler(client, callback_query):
    data = callback_query.data
    
    if data == "help":
        await help_cmd(client, callback_query.message)
    elif data == "about":
        bot_info = await client.get_me()
        await callback_query.message.edit_text(
            f"ℹ️ **About**\n\n"
            f"Bot: @{bot_info.username}\n"
            f"Version: 2.0\n"
            f"Library: Pyrogram + PyTgCalls"
        )
    
    await callback_query.answer()

# Web server
async def health_check(request):
    return web.Response(text="✅ Running")

async def index(request):
    try:
        bot_info = await bot.get_me()
        userbot_status = "✅" if userbot_available else "❌"
        calls_status = "✅" if pytgcalls_available else "❌"
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Music Bot</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        .container {{
            background: rgba(255,255,255,0.15);
            padding: 50px;
            border-radius: 30px;
            backdrop-filter: blur(20px);
            box-shadow: 0 20px 60px rgba(0,0,0,0.4);
            max-width: 600px;
            width: 100%;
            text-align: center;
        }}
        h1 {{ font-size: 4em; margin-bottom: 20px; }}
        .status {{ font-size: 2em; color: #4ade80; margin: 20px 0; }}
        .info {{ margin: 15px 0; font-size: 1.2em; }}
        a {{
            display: inline-block;
            margin-top: 30px;
            padding: 15px 40px;
            background: #4ade80;
            color: white;
            text-decoration: none;
            border-radius: 50px;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎵</h1>
        <div class="status">Music Bot</div>
        <div class="info">🤖 Bot: ✅</div>
        <div class="info">👤 UserBot: {userbot_status}</div>
        <div class="info">🎵 PyTgCalls: {calls_status}</div>
        <div class="info">▶️ Playing: {len(currently_playing)}</div>
        <a href="https://t.me/{bot_info.username}">Start Bot →</a>
    </div>
</body>
</html>
        """
        return web.Response(text=html, content_type='text/html')
    except:
        return web.Response(text="<h1>Loading...</h1>", content_type='text/html')

async def start_web_server():
    app_web = web.Application()
    app_web.router.add_get('/', index)
    app_web.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"✅ Web server: http://0.0.0.0:{PORT}")

# Main
async def main():
    try:
        logger.info("="*60)
        logger.info("🎵 MUSIC BOT STARTING")
        logger.info("="*60)
        
        await start_web_server()
        
        await bot.start()
        bot_info = await bot.get_me()
        logger.info(f"✅ Bot: @{bot_info.username}")
        
        if userbot_available:
            await userbot.start()
            user_info = await userbot.get_me()
            logger.info(f"✅ UserBot: {user_info.first_name}")
            
            if pytgcalls_available:
                await calls.start()
                logger.info(f"✅ PyTgCalls: Ready")
        
        logger.info("="*60)
        logger.info("✅ ALL SYSTEMS OPERATIONAL")
        logger.info("="*60)
        
        await idle()
        
        await bot.stop()
        if userbot_available:
            if pytgcalls_available:
                await calls.stop()
            await userbot.stop()
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())
