import os
import logging
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserAlreadyParticipant, ChatAdminRequired, UserNotParticipant
from dotenv import load_dotenv
from aiohttp import web
import yt_dlp
from typing import Dict, List

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

# Config
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
SESSION_STRING = os.getenv("SESSION_STRING")
PORT = int(os.getenv("PORT", 10000))

# Bot
bot = Client("bot", api_id=int(API_ID), api_hash=API_HASH, bot_token=BOT_TOKEN)

# UserBot
userbot_available = False
if SESSION_STRING:
    try:
        userbot = Client("userbot", api_id=int(API_ID), api_hash=API_HASH, session_string=SESSION_STRING)
        userbot_available = True
        logger.info("✅ UserBot configured")
    except Exception as e:
        logger.error(f"UserBot error: {e}")
        userbot = None
else:
    userbot = None

# PyTgCalls - محاولة استيراد مع دعم إصدارات متعددة
pytgcalls_available = False
calls = None
play_stream = None

if userbot_available:
    try:
        from pytgcalls import PyTgCalls
        calls = PyTgCalls(userbot)
        pytgcalls_available = True
        logger.info("✅ PyTgCalls base imported")
        
        # Try importing different API versions
        try:
            # Try v3.x API
            from pytgcalls.types import AudioPiped
            play_stream = "v3"
            logger.info("✅ Using PyTgCalls v3.x API")
        except ImportError:
            try:
                # Try v2.x API  
                from pytgcalls.types import InputAudioStream, InputStream
                play_stream = "v2"
                logger.info("✅ Using PyTgCalls v2.x API")
            except ImportError:
                try:
                    # Try v1.x API
                    from pytgcalls.types.input_stream import InputAudioStream
                    play_stream = "v1"
                    logger.info("✅ Using PyTgCalls v1.x API")
                except ImportError:
                    logger.warning("⚠️ Could not import stream types")
                    play_stream = "basic"
    except Exception as e:
        logger.error(f"❌ PyTgCalls error: {e}")

# Global data
stats = {'messages': 0, 'commands': 0, 'users': set(), 'groups': set()}
music_queue: Dict[int, List[Dict]] = {}
currently_playing: Dict[int, Dict] = {}
bot_username = None

# ========== HELPER FUNCTIONS ==========

async def join_chat(chat_id: int):
    """إضافة UserBot تلقائياً"""
    if not userbot_available:
        return False
    
    try:
        try:
            await userbot.get_chat_member(chat_id, "me")
            logger.info(f"✅ UserBot in chat {chat_id}")
            return True
        except UserNotParticipant:
            pass
        
        chat = await bot.get_chat(chat_id)
        
        if chat.username:
            try:
                await userbot.join_chat(chat.username)
                logger.info(f"✅ Joined via @{chat.username}")
                return True
            except:
                pass
        
        try:
            invite_link = await bot.export_chat_invite_link(chat_id)
            await userbot.join_chat(invite_link)
            logger.info(f"✅ Joined via invite")
            return True
        except:
            return False
        
    except UserAlreadyParticipant:
        return True
    except Exception as e:
        logger.error(f"Join error: {e}")
        return False

async def play_next_song(chat_id: int):
    """تشغيل الأغنية التالية"""
    if not pytgcalls_available or not calls or not play_stream:
        return False
    
    if chat_id not in music_queue or not music_queue[chat_id]:
        try:
            await calls.leave_group_call(chat_id)
            if chat_id in currently_playing:
                del currently_playing[chat_id]
        except:
            pass
        return False
    
    next_song = music_queue[chat_id].pop(0)
    
    try:
        # Try different API methods based on version
        if play_stream == "v3":
            from pytgcalls.types import AudioPiped
            await calls.join_group_call(chat_id, AudioPiped(next_song['url']))
        elif play_stream == "v2":
            from pytgcalls.types import InputAudioStream, InputStream
            await calls.play(chat_id, InputStream(InputAudioStream(next_song['url'])))
        elif play_stream == "v1":
            from pytgcalls.types.input_stream import InputAudioStream
            await calls.play(chat_id, InputAudioStream(next_song['url']))
        else:
            # Basic fallback
            await calls.play(chat_id, next_song['url'])
        
        currently_playing[chat_id] = next_song
        logger.info(f"▶️ Playing: {next_song['title']}")
        
        try:
            await bot.send_message(chat_id, f"▶️ **الآن:**\n🎵 {next_song['title']}")
        except:
            pass
        
        return True
        
    except Exception as e:
        logger.error(f"Play error: {e}")
        
        if "NO_ACTIVE_GROUP_CALL" in str(e) or "No active" in str(e):
            try:
                await bot.send_message(chat_id, "❌ **لا توجد محادثة صوتية نشطة!**")
            except:
                pass
            return False
        
        return await play_next_song(chat_id)

# Stream end handler - Try different versions
if pytgcalls_available and calls:
    try:
        @calls.on_stream_end()
        async def on_stream_end(client, update):
            try:
                chat_id = update.chat_id
                logger.info(f"Stream ended in {chat_id}")
                await play_next_song(chat_id)
            except Exception as e:
                logger.error(f"Stream end error: {e}")
    except Exception as e:
        logger.warning(f"Could not set stream end handler: {e}")

# YouTube
ydl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'geo_bypass': True,
}

async def download_song(query: str):
    try:
        def extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if query.startswith(('http://', 'https://')):
                    info = ydl.extract_info(query, download=False)
                else:
                    info = ydl.extract_info(f"ytsearch:{query}", download=False)
                    if 'entries' in info and info['entries']:
                        info = info['entries'][0]
                return info
        
        loop = asyncio.get_event_loop()
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

def format_duration(seconds):
    if not seconds:
        return "مباشر"
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d}" if hours else f"{mins:02d}:{secs:02d}"

# Commands
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message: Message):
    stats['messages'] += 1
    stats['users'].add(message.from_user.id)
    
    status = "✅ جاهز" if (userbot_available and pytgcalls_available and play_stream) else "⚠️ محدود"
    
    await message.reply_text(
        f"🎵 **مرحباً {message.from_user.mention}!**\n\n"
        f"**الحالة:** {status}\n\n"
        f"**المميزات:**\n"
        f"{'✅' if userbot_available else '❌'} انضمام تلقائي\n"
        f"{'✅' if pytgcalls_available and play_stream else '❌'} تشغيل فعلي\n"
        f"✅ بحث YouTube\n\n"
        f"**الاستخدام:**\n"
        f"1️⃣ أضفني لقناتك/مجموعتك كمشرف\n"
        f"2️⃣ ابدأ محادثة صوتية/بث\n"
        f"3️⃣ أرسل `/play [اسم الأغنية]`\n\n"
        f"استخدم /help للمزيد"
    )

@bot.on_message(filters.command("ping"))
async def ping_cmd(client, message: Message):
    stats['messages'] += 1
    
    import time
    start = time.time()
    msg = await message.reply_text("🏓")
    end = time.time()
    
    await msg.edit(
        f"🏓 **Pong!**\n\n"
        f"⚡ `{round((end-start)*1000, 2)}ms`\n"
        f"🤖 Bot: ✅\n"
        f"👤 UserBot: {'✅' if userbot_available else '❌'}\n"
        f"🎵 PyTgCalls: {'✅ '+play_stream if pytgcalls_available and play_stream else '❌'}\n"
        f"▶️ Playing: {len(currently_playing)}"
    )

@bot.on_message(filters.command(["play", "p"]) & (filters.group | filters.channel))
async def play_cmd(client, message: Message):
    stats['messages'] += 1
    stats['groups'].add(message.chat.id)
    
    if not userbot_available or not pytgcalls_available or not play_stream:
        return await message.reply_text(
            "❌ **التشغيل غير متاح!**\n\n"
            f"UserBot: {'✅' if userbot_available else '❌'}\n"
            f"PyTgCalls: {'✅' if pytgcalls_available else '❌'}\n"
            f"API: {play_stream or '❌'}"
        )
    
    if len(message.command) < 2:
        return await message.reply_text("❌ استخدم: `/play [اسم الأغنية]`")
    
    query = " ".join(message.command[1:])
    chat_id = message.chat.id
    
    msg = await message.reply_text("🔄 جاري التحضير...")
    
    # Join
    joined = await join_chat(chat_id)
    if not joined:
        return await msg.edit("❌ فشل انضمام العميل المساعد")
    
    await msg.edit("🔍 البحث...")
    
    # Search
    song_info = await download_song(query)
    if not song_info:
        return await msg.edit("❌ لم أجد الأغنية")
    
    # Queue
    if chat_id not in music_queue:
        music_queue[chat_id] = []
    
    music_queue[chat_id].append(song_info)
    position = len(music_queue[chat_id])
    
    # Play if not playing
    if chat_id not in currently_playing:
        await msg.edit("🎵 بدء التشغيل...")
        
        success = await play_next_song(chat_id)
        
        if success:
            await msg.edit(
                f"▶️ **يتم التشغيل:**\n\n"
                f"🎵 {song_info['title']}\n"
                f"⏱️ {format_duration(song_info['duration'])}\n"
                f"🔗 [Link]({song_info['webpage_url']})",
                disable_web_page_preview=False
            )
        else:
            await msg.edit("❌ فشل التشغيل - تأكد من وجود محادثة صوتية نشطة")
    else:
        await msg.edit(
            f"✅ **إضافة #{position}**\n\n"
            f"🎵 {song_info['title']}\n"
            f"⏱️ {format_duration(song_info['duration'])}"
        )

@bot.on_message(filters.command("stop") & (filters.group | filters.channel))
async def stop_cmd(client, message: Message):
    chat_id = message.chat.id
    
    try:
        if pytgcalls_available and calls:
            await calls.leave_group_call(chat_id)
        
        if chat_id in music_queue:
            music_queue[chat_id] = []
        if chat_id in currently_playing:
            del currently_playing[chat_id]
        
        await message.reply_text("⏹️ تم الإيقاف")
    except Exception as e:
        await message.reply_text(f"❌ {str(e)}")

@bot.on_message(filters.command("queue") & (filters.group | filters.channel))
async def queue_cmd(client, message: Message):
    chat_id = message.chat.id
    text = ""
    
    if chat_id in currently_playing:
        text += f"▶️ {currently_playing[chat_id]['title']}\n\n"
    
    if chat_id in music_queue and music_queue[chat_id]:
        text += "📋 القائمة:\n"
        for i, s in enumerate(music_queue[chat_id][:5], 1):
            text += f"{i}. {s['title']}\n"
    
    await message.reply_text(text or "📭 فارغة")

@bot.on_message(filters.command("help"))
async def help_cmd(client, message: Message):
    await message.reply_text(
        "📚 **الأوامر:**\n\n"
        "/play [أغنية] - تشغيل\n"
        "/stop - إيقاف\n"
        "/queue - القائمة\n"
        "/ping - الحالة"
    )

# Web
async def health(request):
    return web.Response(text="OK")

async def index(request):
    return web.Response(text=f"""
<html><body style="font-family:Arial;text-align:center;padding:50px;background:#667eea;color:#fff">
<h1>🎵 Music Bot</h1>
<p style="font-size:2em">{'✅ جاهز' if (userbot_available and pytgcalls_available and play_stream) else '⚠️ محدود'}</p>
<p>UserBot: {'✅' if userbot_available else '❌'}</p>
<p>PyTgCalls: {'✅ '+str(play_stream) if pytgcalls_available and play_stream else '❌'}</p>
<p>Playing: {len(currently_playing)}</p>
</body></html>
    """, content_type='text/html')

async def start_web():
    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_get('/health', health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()
    logger.info(f"✅ Web on {PORT}")

# Main
async def main():
    global bot_username
    
    logger.info("🎵 MUSIC BOT")
    
    await bot.start()
    me = await bot.get_me()
    bot_username = me.username
    logger.info(f"✅ Bot: @{me.username}")
    
    if userbot_available:
        await userbot.start()
        user_info = await userbot.get_me()
        logger.info(f"✅ UserBot: {user_info.first_name}")
        
        if pytgcalls_available:
            try:
                await calls.start()
                logger.info(f"✅ PyTgCalls started ({play_stream})")
                if play_stream:
                    logger.info("🎉 FULL PLAYBACK READY!")
            except Exception as e:
                logger.error(f"PyTgCalls start error: {e}")
    
    await start_web()
    logger.info("✅ READY!")
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    bot.run(main())
