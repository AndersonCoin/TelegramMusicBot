import os
import logging
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatMemberStatus
from dotenv import load_dotenv
from aiohttp import web
import yt_dlp
from typing import Dict, List

# Load environment
load_dotenv()

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment variables
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
SESSION_STRING = os.getenv("SESSION_STRING")
PORT = int(os.getenv("PORT", 10000))

if not all([API_ID, API_HASH, BOT_TOKEN]):
    logger.error("Missing required environment variables!")
    exit(1)

# Bot client
bot = Client(
    "MusicBot",
    api_id=int(API_ID),
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

# UserBot client
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
    logger.warning("⚠️ SESSION_STRING not found - Music playback disabled")
    userbot = None

# Try to import pytgcalls
try:
    from pytgcalls import PyTgCalls
    from pytgcalls.types import Update
    from pytgcalls.types.input_stream import InputAudioStream, InputStream
    from pytgcalls.types.stream import StreamAudioEnded
    
    if userbot_available:
        calls = PyTgCalls(userbot)
        pytgcalls_available = True
        logger.info("✅ PyTgCalls imported successfully")
    else:
        calls = None
        pytgcalls_available = False
except ImportError as e:
    logger.warning(f"⚠️ PyTgCalls not available: {e}")
    calls = None
    pytgcalls_available = False

# Global data
music_queue: Dict[int, List[Dict]] = {}
currently_playing: Dict[int, Dict] = {}

# YouTube options
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
        
        def extract_info():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if query.startswith(('http://', 'https://')):
                    info = ydl.extract_info(query, download=False)
                else:
                    info = ydl.extract_info(f"ytsearch:{query}", download=False)
                    if 'entries' in info and info['entries']:
                        info = info['entries'][0]
                return info
        
        info = await loop.run_in_executor(None, extract_info)
        
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
    if not pytgcalls_available:
        return
    
    if chat_id not in music_queue or not music_queue[chat_id]:
        try:
            await calls.leave_call(chat_id)
            if chat_id in currently_playing:
                del currently_playing[chat_id]
        except:
            pass
        return
    
    next_song = music_queue[chat_id].pop(0)
    
    try:
        await calls.play(
            chat_id,
            InputStream(
                InputAudioStream(
                    next_song['url'],
                )
            )
        )
        currently_playing[chat_id] = next_song
        logger.info(f"▶️ Now playing: {next_song['title']}")
    except Exception as e:
        logger.error(f"Play error: {e}")
        await play_next_song(chat_id)

# Stream ended handler
if pytgcalls_available:
    @calls.on_stream_end()
    async def on_stream_end(client, update: Update):
        if isinstance(update, StreamAudioEnded):
            chat_id = update.chat_id
            logger.info(f"Stream ended in {chat_id}")
            await play_next_song(chat_id)

# Bot commands
@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    status = "✅ Available" if (userbot_available and pytgcalls_available) else "❌ Not Available"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add to Group", 
            url=f"https://t.me/{(await client.get_me()).username}?startgroup=true")],
        [InlineKeyboardButton("📚 Help", callback_data="help"),
         InlineKeyboardButton("ℹ️ About", callback_data="about")],
        [InlineKeyboardButton("💡 Support", url="https://t.me/your_support")]
    ])
    
    await message.reply_text(
        f"🎵 **Welcome to Music Bot!**\n\n"
        f"**Status:**\n"
        f"🤖 Bot: ✅ Online\n"
        f"🎶 Music: {status}\n\n"
        f"**Commands:**\n"
        f"• /play [song] - Play a song\n"
        f"• /help - Show all commands\n\n"
        f"**Setup:**\n"
        f"1. Add me to your group\n"
        f"2. Make me admin\n"
        f"3. Start voice chat\n"
        f"4. Use /play command\n\n"
        f"Enjoy the music! 🎶",
        reply_markup=keyboard
    )

@bot.on_message(filters.command("help"))
async def help_cmd(client, message):
    help_text = """
📚 **Music Bot Help**

**🎵 Music Commands:**
• `/play [song/link]` - Play a song
• `/pause` - Pause playback
• `/resume` - Resume playback
• `/skip` - Skip current song
• `/stop` - Stop and clear queue
• `/queue` - Show queue
• `/current` - Current song

**ℹ️ Info Commands:**
• `/start` - Start bot
• `/help` - This message
• `/ping` - Check status
• `/stats` - Statistics

**Requirements:**
✅ Bot must be admin
✅ Voice chat must be active
✅ UserBot must be configured

Need help? Contact support!
"""
    await message.reply_text(help_text)

@bot.on_message(filters.command("ping"))
async def ping_cmd(client, message):
    import time
    start = time.time()
    msg = await message.reply_text("🏓 Pinging...")
    end = time.time()
    latency = round((end - start) * 1000, 2)
    
    userbot_status = "✅ Online" if userbot_available else "❌ Offline"
    calls_status = "✅ Online" if pytgcalls_available else "❌ Offline"
    
    await msg.edit(
        f"🏓 **Pong!**\n\n"
        f"⚡ **Latency:** `{latency}ms`\n"
        f"🤖 **Bot:** ✅ Online\n"
        f"👤 **UserBot:** {userbot_status}\n"
        f"🎵 **PyTgCalls:** {calls_status}\n"
        f"💬 **Active Chats:** {len(currently_playing)}"
    )

@bot.on_message(filters.command("stats"))
async def stats_cmd(client, message):
    total_chats = len(music_queue)
    total_playing = len(currently_playing)
    total_queued = sum(len(q) for q in music_queue.values())
    
    await message.reply_text(
        f"📊 **Bot Statistics**\n\n"
        f"💬 **Total Chats:** {total_chats}\n"
        f"▶️ **Currently Playing:** {total_playing}\n"
        f"📋 **Queued Songs:** {total_queued}\n"
        f"✅ **Status:** Online\n"
        f"🎵 **Version:** 2.0.0"
    )

@bot.on_message(filters.command(["play", "p"]) & filters.group)
async def play_cmd(client, message):
    if not userbot_available or not pytgcalls_available:
        return await message.reply_text(
            "❌ **Music playback unavailable!**\n\n"
            "Reason: UserBot or PyTgCalls not configured.\n"
            "Contact the bot owner to enable music playback."
        )
    
    if len(message.command) < 2:
        return await message.reply_text(
            "❌ **Usage:**\n`/play [song name or YouTube link]`\n\n"
            "**Example:**\n`/play Imagine Dragons Believer`"
        )
    
    query = " ".join(message.command[1:])
    chat_id = message.chat.id
    
    msg = await message.reply_text("🔍 **Searching...**")
    
    # Download song
    song_info = await download_song(query)
    
    if not song_info:
        return await msg.edit("❌ **Song not found!**\nTry a different search term.")
    
    # Add to queue
    if chat_id not in music_queue:
        music_queue[chat_id] = []
    
    music_queue[chat_id].append(song_info)
    position = len(music_queue[chat_id])
    
    # If not playing, start
    if chat_id not in currently_playing:
        await msg.edit("🎵 **Joining voice chat...**")
        try:
            await play_next_song(chat_id)
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⏸️ Pause", callback_data=f"pause_{chat_id}"),
                 InlineKeyboardButton("⏭️ Skip", callback_data=f"skip_{chat_id}")],
                [InlineKeyboardButton("⏹️ Stop", callback_data=f"stop_{chat_id}"),
                 InlineKeyboardButton("📋 Queue", callback_data=f"queue_{chat_id}")]
            ])
            
            await msg.edit(
                f"▶️ **Now Playing:**\n\n"
                f"🎵 **{song_info['title']}**\n"
                f"👤 **Uploader:** {song_info['uploader']}\n"
                f"⏱️ **Duration:** {format_duration(song_info['duration'])}\n"
                f"🔗 [YouTube Link]({song_info['webpage_url']})\n\n"
                f"👤 Requested by: {message.from_user.mention}",
                reply_markup=keyboard,
                disable_web_page_preview=False
            )
        except Exception as e:
            error_msg = str(e)
            if "No active group call" in error_msg:
                await msg.edit(
                    "❌ **No active voice chat!**\n\n"
                    "Please start a voice chat first, then try again."
                )
            else:
                await msg.edit(f"❌ **Error:** {error_msg}")
            logger.error(f"Play error: {e}")
    else:
        await msg.edit(
            f"✅ **Added to Queue #{position}**\n\n"
            f"🎵 **{song_info['title']}**\n"
            f"⏱️ **Duration:** {format_duration(song_info['duration'])}\n"
            f"👤 Requested by: {message.from_user.mention}"
        )

@bot.on_message(filters.command("pause") & filters.group)
async def pause_cmd(client, message):
    if not pytgcalls_available:
        return await message.reply_text("❌ PyTgCalls not available")
    
    try:
        await calls.pause_stream(message.chat.id)
        await message.reply_text("⏸️ **Playback paused**")
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

@bot.on_message(filters.command("resume") & filters.group)
async def resume_cmd(client, message):
    if not pytgcalls_available:
        return await message.reply_text("❌ PyTgCalls not available")
    
    try:
        await calls.resume_stream(message.chat.id)
        await message.reply_text("▶️ **Playback resumed**")
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

@bot.on_message(filters.command("skip") & filters.group)
async def skip_cmd(client, message):
    if not pytgcalls_available:
        return await message.reply_text("❌ PyTgCalls not available")
    
    chat_id = message.chat.id
    
    if chat_id not in currently_playing:
        return await message.reply_text("❌ Nothing is playing!")
    
    await message.reply_text("⏭️ **Skipping...**")
    await play_next_song(chat_id)

@bot.on_message(filters.command("stop") & filters.group)
async def stop_cmd(client, message):
    if not pytgcalls_available:
        return await message.reply_text("❌ PyTgCalls not available")
    
    chat_id = message.chat.id
    
    try:
        await calls.leave_call(chat_id)
        
        if chat_id in music_queue:
            music_queue[chat_id] = []
        if chat_id in currently_playing:
            del currently_playing[chat_id]
        
        await message.reply_text("⏹️ **Stopped and cleared queue**")
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

@bot.on_message(filters.command("queue") & filters.group)
async def queue_cmd(client, message):
    chat_id = message.chat.id
    
    if chat_id not in currently_playing and (chat_id not in music_queue or not music_queue[chat_id]):
        return await message.reply_text("📭 **Queue is empty**")
    
    text = "📋 **Music Queue:**\n\n"
    
    if chat_id in currently_playing:
        current = currently_playing[chat_id]
        text += f"▶️ **Now Playing:**\n{current['title']}\n⏱️ {format_duration(current['duration'])}\n\n"
    
    if chat_id in music_queue and music_queue[chat_id]:
        text += "**Up Next:**\n"
        for i, song in enumerate(music_queue[chat_id][:10], 1):
            text += f"{i}. {song['title']}\n   ⏱️ {format_duration(song['duration'])}\n"
        
        if len(music_queue[chat_id]) > 10:
            text += f"\n_...and {len(music_queue[chat_id]) - 10} more_"
    
    await message.reply_text(text)

@bot.on_message(filters.command("current") & filters.group)
async def current_cmd(client, message):
    chat_id = message.chat.id
    
    if chat_id not in currently_playing:
        return await message.reply_text("❌ Nothing is playing!")
    
    song = currently_playing[chat_id]
    await message.reply_text(
        f"▶️ **Now Playing:**\n\n"
        f"🎵 **{song['title']}**\n"
        f"👤 **Uploader:** {song['uploader']}\n"
        f"⏱️ **Duration:** {format_duration(song['duration'])}\n"
        f"🔗 [YouTube Link]({song['webpage_url']})",
        disable_web_page_preview=False
    )

# Callback handler
@bot.on_callback_query()
async def callback_handler(client, callback_query):
    data = callback_query.data
    
    if data == "help":
        await callback_query.message.edit_text(
            "📚 **Help**\n\nUse /help command for full list of commands.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="back")
            ]])
        )
    elif data == "about":
        bot_info = await client.get_me()
        await callback_query.message.edit_text(
            f"ℹ️ **About**\n\n"
            f"Bot: @{bot_info.username}\n"
            f"Version: 2.0.0\n"
            f"Library: Pyrogram + PyTgCalls",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="back")
            ]])
        )
    elif data == "back":
        await start_cmd(client, callback_query.message)
    
    await callback_query.answer()

# Web server
async def health_check(request):
    return web.Response(text="✅ Bot is running!")

async def index(request):
    try:
        bot_info = await bot.get_me()
        userbot_status = "✅ Online" if userbot_available else "❌ Offline"
        calls_status = "✅ Ready" if pytgcalls_available else "❌ Not Ready"
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Music Bot - Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
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
            max-width: 700px;
            width: 100%;
        }}
        h1 {{
            font-size: 4em;
            text-align: center;
            margin-bottom: 10px;
            text-shadow: 3px 3px 6px rgba(0,0,0,0.3);
        }}
        .subtitle {{
            text-align: center;
            font-size: 1.5em;
            margin-bottom: 40px;
            opacity: 0.9;
        }}
        .status-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
            margin: 30px 0;
        }}
        .status-card {{
            background: rgba(255,255,255,0.1);
            padding: 25px;
            border-radius: 15px;
            text-align: center;
        }}
        .status-card h3 {{
            font-size: 0.9em;
            opacity: 0.8;
            margin-bottom: 10px;
        }}
        .status-card .value {{
            font-size: 1.8em;
            font-weight: bold;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin: 30px 0;
        }}
        .stat {{
            background: rgba(255,255,255,0.1);
            padding: 20px;
            border-radius: 15px;
            text-align: center;
        }}
        .stat-number {{
            font-size: 2.5em;
            font-weight: bold;
            color: #4ade80;
            margin-bottom: 5px;
        }}
        .stat-label {{
            font-size: 0.9em;
            opacity: 0.8;
        }}
        .bot-link {{
            display: block;
            text-align: center;
            margin-top: 30px;
            padding: 18px;
            background: linear-gradient(135deg, #4ade80, #22c55e);
            color: white;
            text-decoration: none;
            border-radius: 50px;
            font-size: 1.4em;
            font-weight: bold;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .bot-link:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(74,222,128,0.4);
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎵</h1>
        <div class="subtitle">Music Bot Dashboard</div>
        
        <div class="status-grid">
            <div class="status-card">
                <h3>🤖 BOT STATUS</h3>
                <div class="value">✅ Online</div>
            </div>
            <div class="status-card">
                <h3>👤 USERBOT</h3>
                <div class="value">{userbot_status}</div>
            </div>
            <div class="status-card">
                <h3>🎵 MUSIC ENGINE</h3>
                <div class="value">{calls_status}</div>
            </div>
            <div class="status-card">
                <h3>📡 USERNAME</h3>
                <div class="value" style="font-size: 1.3em;">@{bot_info.username}</div>
            </div>
        </div>
        
        <div class="stats">
            <div class="stat">
                <div class="stat-number">{len(currently_playing)}</div>
                <div class="stat-label">Playing Now</div>
            </div>
            <div class="stat">
                <div class="stat-number">{sum(len(q) for q in music_queue.values())}</div>
                <div class="stat-label">In Queue</div>
            </div>
            <div class="stat">
                <div class="stat-number">{len(music_queue)}</div>
                <div class="stat-label">Active Chats</div>
            </div>
        </div>
        
        <a href="https://t.me/{bot_info.username}" class="bot-link">
            🚀 Start Bot
        </a>
    </div>
</body>
</html>
        """
        return web.Response(text=html, content_type='text/html')
    except Exception as e:
        return web.Response(text=f"<h1>Loading...</h1><p>{str(e)}</p>", content_type='text/html')

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
        logger.info("="*70)
        logger.info("🎵 MUSIC BOT - STARTING UP")
        logger.info("="*70)
        
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
        
        logger.info("="*70)
        logger.info("✅ ALL SYSTEMS OPERATIONAL!")
        logger.info("="*70)
        
        await idle()
        
        await bot.stop()
        if userbot_available:
            if pytgcalls_available:
                await calls.stop()
            await userbot.stop()
        
        logger.info("Bot stopped")
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
