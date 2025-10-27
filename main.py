import os
import logging
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserAlreadyParticipant, ChatAdminRequired, UserNotParticipant
from dotenv import load_dotenv
from aiohttp import web
import yt_dlp
from typing import Dict, List
import time

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
    logger.warning("⚠️ No UserBot - Add SESSION_STRING for music playback")

# py-tgcalls setup
pytgcalls_available = False
calls = None

if userbot_available:
    try:
        # **التعديل هنا:** تم تغيير "py_tgcalls" إلى "pytgcalls"
        from pytgcalls import PyTgCalls
        
        calls = PyTgCalls(userbot)
        pytgcalls_available = True
        logger.info("✅ pytgcalls imported successfully")
    except ImportError as e:
        # **تم تحديث رسالة الخطأ لتكون أكثر دقة**
        logger.error(f"❌ pytgcalls import error: {e}")
        logger.error("Install: pip install py-tgcalls")
    except Exception as e:
        logger.error(f"❌ pytgcalls error: {e}")

# Global data
stats = {
    'messages': 0,
    'commands': 0,
    'users': set(),
    'groups': set(),
    'songs_searched': 0,
    'songs_played': 0,
    'start_time': time.time()
}

music_queue: Dict[int, List[Dict]] = {}
currently_playing: Dict[int, Dict] = {}
bot_username = None

# YouTube downloader
ydl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'geo_bypass': True,
    'ignoreerrors': True,
}

async def download_song(query: str):
    """بحث وتحميل معلومات الأغنية من YouTube"""
    try:
        logger.info(f"🔍 Searching: {query}")
        stats['songs_searched'] += 1
        
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
            'uploader': info.get('uploader', 'Unknown'),
            'view_count': info.get('view_count', 0),
            'like_count': info.get('like_count', 0)
        }
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None

def format_duration(seconds):
    """تنسيق المدة الزمنية"""
    if not seconds:
        return "مباشر"
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d}" if hours else f"{mins:02d}:{secs:02d}"

def format_number(num):
    """تنسيق الأرقام"""
    if not num:
        return "0"
    if num >= 1_000_000:
        return f"{num/1_000_000:.1f}M"
    if num >= 1_000:
        return f"{num/1_000:.1f}K"
    return str(num)

async def join_chat(chat_id: int):
    """إضافة UserBot للمجموعة/القناة تلقائياً"""
    if not userbot_available:
        return False
    
    try:
        try:
            await userbot.get_chat_member(chat_id, "me")
            logger.info(f"✅ UserBot already in {chat_id}")
            return True
        except UserNotParticipant:
            pass
        
        chat = await bot.get_chat(chat_id)
        
        if chat.username:
            try:
                await userbot.join_chat(chat.username)
                logger.info(f"✅ Joined @{chat.username}")
                return True
            except Exception as e:
                logger.error(f"Join via username failed: {e}")
        
        try:
            invite_link = await bot.export_chat_invite_link(chat_id)
            await userbot.join_chat(invite_link)
            logger.info(f"✅ Joined via invite")
            return True
        except ChatAdminRequired:
            logger.error("❌ Need admin rights")
            return False
        except Exception as e:
            logger.error(f"Join via invite failed: {e}")
            return False
        
    except UserAlreadyParticipant:
        return True
    except Exception as e:
        logger.error(f"Join error: {e}")
        return False

async def play_next_song(chat_id: int):
    """تشغيل الأغنية التالية في القائمة"""
    if not pytgcalls_available or not calls:
        logger.warning("⚠️ pytgcalls not available")
        return False
    
    # Check queue
    if chat_id not in music_queue or not music_queue[chat_id]:
        # Queue empty - leave call
        try:
            await calls.leave_group_call(chat_id)
            if chat_id in currently_playing:
                del currently_playing[chat_id]
            logger.info(f"🔚 Queue empty, left chat {chat_id}")
            
            # Notify in chat
            try:
                await bot.send_message(chat_id, "📭 **انتهت قائمة الانتظار**")
            except:
                pass
        except Exception as e:
            logger.error(f"Leave call error: {e}")
        return False
    
    # Get next song
    next_song = music_queue[chat_id].pop(0)
    
    try:
        # Play using pytgcalls
        await calls.play(
            chat_id,
            next_song['url']
        )
        
        currently_playing[chat_id] = next_song
        stats['songs_played'] += 1
        logger.info(f"▶️ Now playing: {next_song['title']}")
        
        # Notify in chat
        try:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data=f"pause_{chat_id}"),
                 InlineKeyboardButton("⏭️ تخطي", callback_data=f"skip_{chat_id}")],
                [InlineKeyboardButton("⏹️ إيقاف", callback_data=f"stop_{chat_id}"),
                 InlineKeyboardButton("🎵 YouTube", url=next_song['webpage_url'])]
            ])
            
            await bot.send_message(
                chat_id,
                f"▶️ **يتم التشغيل الآن:**\n\n"
                f"🎵 **{next_song['title']}**\n"
                f"👤 {next_song['uploader']}\n"
                f"⏱️ {format_duration(next_song['duration'])}",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Notification error: {e}")
        
        return True
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Play error: {error_msg}")
        
        # Handle specific errors
        if "NO_ACTIVE_GROUP_CALL" in error_msg or "No active" in error_msg or "GROUP_CALL" in error_msg:
            logger.error("❌ No voice chat active!")
            try:
                await bot.send_message(
                    chat_id,
                    "❌ **لا توجد محادثة صوتية نشطة!**\n\n"
                    "ابدأ محادثة صوتية/بث مباشر أولاً ثم جرب مرة أخرى."
                )
            except:
                pass
            return False
        
        # Try next song on other errors
        logger.info("Trying next song...")
        return await play_next_song(chat_id)

# Stream ended callback for pytgcalls
if pytgcalls_available and calls:
    @calls.on_stream_end()
    async def on_stream_end(client, update):
        """عند انتهاء الأغنية"""
        try:
            chat_id = update.chat_id
            logger.info(f"🔚 Stream ended in {chat_id}")
            
            # Notify
            if chat_id in currently_playing:
                ended_song = currently_playing[chat_id]
                try:
                    await bot.send_message(
                        chat_id,
                        f"✅ **انتهى تشغيل:**\n🎵 {ended_song['title']}"
                    )
                except:
                    pass
            
            # Play next
            await play_next_song(chat_id)
            
        except Exception as e:
            logger.error(f"Stream end handler error: {e}")

# ========== COMMANDS ==========

@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message: Message):
    stats['messages'] += 1
    stats['users'].add(message.from_user.id)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ أضفني لمجموعتك/قناتك", 
            url=f"https://t.me/{bot_username}?startgroup=true")],
        [InlineKeyboardButton("📚 الأوامر", callback_data="help"),
         InlineKeyboardButton("📊 الإحصائيات", callback_data="stats")],
        [InlineKeyboardButton("ℹ️ حول البوت", callback_data="about")]
    ])
    
    playback_status = "✅ التشغيل الفعلي متاح" if (userbot_available and pytgcalls_available) else "⚠️ عرض معلومات فقط"
    
    await message.reply_text(
        f"🎵 **مرحباً {message.from_user.mention}!**\n\n"
        f"أنا بوت تشغيل الموسيقى في القنوات والمجموعات\n\n"
        f"**الحالة:** {playback_status}\n\n"
        f"**المميزات:**\n"
        f"✅ {'تشغيل فعلي في المحادثات الصوتية' if pytgcalls_available else 'معلومات وروابط الأغاني'}\n"
        f"✅ {'انضمام تلقائي للمجموعات/القنوات' if userbot_available else 'دعم المجموعات'}\n"
        f"✅ بحث متقدم في YouTube\n"
        f"✅ قوائم انتظار ذكية\n"
        f"✅ انتقال تلقائي بين الأغاني\n"
        f"✅ إحصائيات مفصلة\n\n"
        f"**للبدء:**\n"
        f"1️⃣ أضفني لقناتك/مجموعتك كمشرف\n"
        f"2️⃣ ابدأ محادثة صوتية أو بث مباشر\n"
        f"3️⃣ استخدم `/play [اسم الأغنية]`\n\n"
        f"{'🎉 سينضم العميل المساعد ويشغل الموسيقى تلقائياً!' if (userbot_available and pytgcalls_available) else '💡 أضف SESSION_STRING للتشغيل الفعلي'}\n\n"
        f"اضغط على الأزرار أدناه للمزيد 👇",
        reply_markup=keyboard
    )

@bot.on_message(filters.command("help"))
async def help_cmd(client, message: Message):
    stats['messages'] += 1
    
    help_text = f"""
📚 **دليل الاستخدام الكامل**

**🎵 أوامر الموسيقى:**
• `/play [أغنية]` - {'تشغيل أغنية' if pytgcalls_available else 'البحث عن أغنية'}
• `/search [اسم]` - بحث متقدد (5 نتائج)
• `/pause` - إيقاف مؤقت {'✅' if pytgcalls_available else '❌'}
• `/resume` - استئناف التشغيل {'✅' if pytgcalls_available else '❌'}
• `/skip` - تخطي الأغنية {'✅' if pytgcalls_available else '❌'}
• `/stop` - إيقاف وحذف القائمة {'✅' if pytgcalls_available else '❌'}
• `/queue` - عرض قائمة الانتظار
• `/current` - الأغنية الحالية
• `/clear` - حذف القائمة

**ℹ️ أوامر المعلومات:**
• `/start` - بدء البوت
• `/help` - هذه المساعدة
• `/ping` - فحص السرعة
• `/stats` - الإحصائيات
• `/id` - معرف المستخدم/المجموعة

**💡 أمثلة:**
• `/play فيروز صباح الخير`
• `/play Imagine Dragons Believer`
• `/search عبدالحليم حافظ`
• `/play https://youtube.com/watch?v=...`

**📝 ملاحظات:**
• {'للتشغيل الفعلي: ابدأ محادثة صوتية أولاً' if pytgcalls_available else 'التشغيل الفعلي غير متاح - يمكنك الاستماع عبر روابط YouTube'}
• البوت يعمل في المجموعات والقنوات
• {'العميل المساعد ينضم تلقائياً' if userbot_available else 'أضف البوت كمشرف'}
"""
    await message.reply_text(help_text)

@bot.on_message(filters.command("ping"))
async def ping_cmd(client, message: Message):
    stats['messages'] += 1
    
    start = time.time()
    msg = await message.reply_text("🏓 جاري الفحص...")
    end = time.time()
    latency = round((end - start) * 1000, 2)
    
    uptime = time.time() - stats['start_time']
    hours = int(uptime // 3600)
    mins = int((uptime % 3600) // 60)
    
    await msg.edit(
        f"🏓 **Pong!**\n\n"
        f"⚡ **السرعة:** `{latency}ms`\n"
        f"🤖 **البوت:** ✅ نشط\n"
        f"👤 **UserBot:** {'✅ متصل' if userbot_available else '❌ غير متصل'}\n"
        f"🎵 **pytgcalls:** {'✅ جاهز' if pytgcalls_available else '❌ غير متاح'}\n"
        f"⏱️ **وقت التشغيل:** {hours}h {mins}m\n"
        f"📊 **الرسائل:** {stats['messages']}\n"
        f"🔍 **الأغاني المبحوثة:** {stats['songs_searched']}\n"
        f"▶️ **الأغاني المشغلة:** {stats['songs_played']}\n"
        f"🎶 **قيد التشغيل الآن:** {len(currently_playing)}"
    )

@bot.on_message(filters.command("stats"))
async def stats_cmd(client, message: Message):
    stats['messages'] += 1
    
    uptime = time.time() - stats['start_time']
    hours = int(uptime // 3600)
    mins = int((uptime % 3600) // 60)
    
    await message.reply_text(
        f"📊 **إحصائيات البوت**\n\n"
        f"**👥 المستخدمون:**\n"
        f"• إجمالي المستخدمين: {len(stats['users'])}\n"
        f"• المجموعات/القنوات: {len(stats['groups'])}\n\n"
        f"**📈 النشاط:**\n"
        f"• إجمالي الرسائل: {stats['messages']}\n"
        f"• الأوامر المنفذة: {stats['commands']}\n"
        f"• الأغاني المبحوثة: {stats['songs_searched']}\n"
        f"• الأغاني المشغلة: {stats['songs_played']}\n\n"
        f"**⏱️ النظام:**\n"
        f"• وقت التشغيل: {hours}h {mins}m\n"
        f"• قوائم الانتظار: {len(music_queue)}\n"
        f"• قيد التشغيل: {len(currently_playing)}\n"
        f"• في الانتظار: {sum(len(q) for q in music_queue.values())}\n\n"
        f"**🔧 الحالة:**\n"
        f"• البوت: ✅ نشط\n"
        f"• UserBot: {'✅ متصل' if userbot_available else '❌ غير متصل'}\n"
        f"• pytgcalls: {'✅ جاهز' if pytgcalls_available else '❌ غير متاح'}\n"
        f"• التشغيل الفعلي: {'✅ متاح' if (userbot_available and pytgcalls_available) else '❌ غير متاح'}"
    )

@bot.on_message(filters.command("id"))
async def id_cmd(client, message: Message):
    stats['messages'] += 1
    
    text = f"**🆔 معلومات المعرفات:**\n\n"
    text += f"👤 **معرفك:** `{message.from_user.id}`\n"
    text += f"📛 **اسمك:** {message.from_user.first_name}\n"
    
    if message.from_user.username:
        text += f"🔗 **يوزرك:** @{message.from_user.username}\n"
    
    if message.chat.type != "private":
        text += f"\n💬 **معرف المجموعة/القناة:** `{message.chat.id}`\n"
        if message.chat.title:
            text += f"📝 **الاسم:** {message.chat.title}\n"
        if message.chat.username:
            text += f"🔗 **الرابط:** @{message.chat.username}"
    
    await message.reply_text(text)

@bot.on_message(filters.command(["play", "p"]))
async def play_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    if message.chat.type != "private":
        stats['groups'].add(message.chat.id)
    
    if len(message.command) < 2:
        return await message.reply_text(
            "❌ **الاستخدام:**\n"
            "`/play [اسم الأغنية أو رابط YouTube]`\n\n"
            "**أمثلة:**\n"
            "• `/play فيروز صباح الخير`\n"
            "• `/play Imagine Dragons Believer`\n"
            "• `/play https://youtube.com/watch?v=...`"
        )
    
    query = " ".join(message.command[1:])
    chat_id = message.chat.id
    
    # For groups/channels only
    if message.chat.type == "private":
        msg = await message.reply_text("🔍 **جاري البحث...**")
        song_info = await download_song(query)
        
        if not song_info:
            return await msg.edit("❌ **لم أجد الأغنية!**")
        
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎵 استمع على YouTube", url=song_info['webpage_url'])
        ]])
        
        if song_info.get('thumbnail'):
            try:
                await msg.delete()
                await message.reply_photo(
                    photo=song_info['thumbnail'],
                    caption=f"🎵 **{song_info['title']}**\n"
                            f"👤 {song_info['uploader']}\n"
                            f"⏱️ {format_duration(song_info['duration'])}\n"
                            f"👁️ {format_number(song_info.get('view_count', 0))} مشاهدة",
                    reply_markup=keyboard
                )
            except:
                await msg.edit(
                    f"🎵 **{song_info['title']}**\n"
                    f"👤 {song_info['uploader']}\n"
                    f"⏱️ {format_duration(song_info['duration'])}\n"
                    f"🔗 [YouTube]({song_info['webpage_url']})",
                    reply_markup=keyboard
                )
        return
    
    # For groups/channels
    msg = await message.reply_text(
        "🔄 **جاري التحضير...**\n"
        f"{'⏳ إضافة العميل المساعد...' if userbot_available else '🔍 البحث...'}"
    )
    
    # Join chat if userbot available
    if userbot_available:
        joined = await join_chat(chat_id)
        if not joined:
            return await msg.edit(
                "❌ **فشل انضمام العميل المساعد!**\n\n"
                "**تأكد من:**\n"
                "• البوت مشرف\n"
                "• صلاحية دعوة المستخدمين\n"
                "• القناة/المجموعة عامة أو لديك صلاحيات"
            )
        await msg.edit("🔍 **جاري البحث...**")
    
    # Search song
    song_info = await download_song(query)
    
    if not song_info:
        return await msg.edit("❌ **لم أجد الأغنية!**")
    
    # Add to queue
    if chat_id not in music_queue:
        music_queue[chat_id] = []
    
    music_queue[chat_id].append(song_info)
    position = len(music_queue[chat_id])
    
    # Try playing if pytgcalls available
    if pytgcalls_available and chat_id not in currently_playing:
        await msg.edit("🎵 **بدء التشغيل...**")
        
        success = await play_next_song(chat_id)
        
        if success:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⏸️ إيقاف", callback_data=f"pause_{chat_id}"),
                 InlineKeyboardButton("⏭️ تخطي", callback_data=f"skip_{chat_id}")],
                [InlineKeyboardButton("⏹️ إيقاف كامل", callback_data=f"stop_{chat_id}"),
                 InlineKeyboardButton("📋 القائمة", callback_data=f"queue_{chat_id}")],
                [InlineKeyboardButton("🎵 YouTube", url=song_info['webpage_url'])]
            ])
            
            caption = (
                f"▶️ **يتم التشغيل الآن:**\n\n"
                f"🎵 **{song_info['title']}**\n"
                f"👤 {song_info['uploader']}\n"
                f"⏱️ {format_duration(song_info['duration'])}\n"
                f"👁️ {format_number(song_info.get('view_count', 0))} مشاهدة\n\n"
                f"👤 **طلب بواسطة:** {message.from_user.mention if message.from_user else 'مجهول'}\n"
                f"🤖 **العميل:** انضم وبدأ التشغيل تلقائياً ✅"
            )
            
            try:
                await msg.delete()
                if song_info.get('thumbnail'):
                    await message.reply_photo(
                        photo=song_info['thumbnail'],
                        caption=caption,
                        reply_markup=keyboard
                    )
                else:
                    await message.reply_text(caption, reply_markup=keyboard)
            except:
                await msg.edit(caption, reply_markup=keyboard)
        else:
            await msg.edit(
                "❌ **فشل التشغيل!**\n\n"
                "**تأكد من:**\n"
                "• وجود محادثة صوتية/بث نشط\n"
                "• البوت والعميل مشرفين\n"
                "• صلاحيات إدارة المحادثة الصوتية"
            )
    else:
        # Just add to queue or show info
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎵 YouTube", url=song_info['webpage_url'])
        ]])
        
        caption = (
            f"✅ **تمت الإضافة للقائمة #{position}**\n\n"
            f"🎵 **{song_info['title']}**\n"
            f"👤 {song_info['uploader']}\n"
            f"⏱️ {format_duration(song_info['duration'])}\n"
            f"👁️ {format_number(song_info.get('view_count', 0))} مشاهدة\n\n"
            f"{'سيتم تشغيلها بعد الأغنية الحالية' if pytgcalls_available else '💡 اضغط الزر للاستماع على YouTube'}"
        )
        
        try:
            await msg.delete()
            if song_info.get('thumbnail'):
                await message.reply_photo(
                    photo=song_info['thumbnail'],
                    caption=caption,
                    reply_markup=keyboard
                )
            else:
                await message.reply_text(caption, reply_markup=keyboard)
        except:
            await msg.edit(caption, reply_markup=keyboard)

@bot.on_message(filters.command(["search", "s"]))
async def search_cmd(client, message: Message):
    stats['messages'] += 1
    stats['commands'] += 1
    
    if len(message.command) < 2:
        return await message.reply_text("❌ **الاستخدام:** `/search [اسم الأغنية]`")
    
    query = " ".join(message.command[1:])
    msg = await message.reply_text("🔍 **جاري البحث...**")
    
    try:
        def extract_multi():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch5:{query}", download=False)
                return info.get('entries', [])
        
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, extract_multi)
        
        if not results:
            return await msg.edit("❌ **لم أجد نتائج!**")
        
        text = f"🔍 **نتائج البحث عن:** `{query}`\n\n"
        
        for i, result in enumerate(results[:5], 1):
            text += f"**{i}.** {result.get('title', 'Unknown')}\n"
            text += f"   👤 {result.get('uploader', 'Unknown')}\n"
            text += f"   ⏱️ {format_duration(result.get('duration', 0))}\n"
            text += f"   🔗 {result.get('webpage_url', '')}\n\n"
        
        text += "💡 **استخدم** `/play [رابط]` **لتشغيل/إضافة أغنية**"
        
        await msg.edit(text, disable_web_page_preview=True)
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        await msg.edit(f"❌ **خطأ في البحث**")

@bot.on_message(filters.command("pause") & (filters.group | filters.channel))
async def pause_cmd(client, message: Message):
    stats['messages'] += 1
    
    if not pytgcalls_available:
        return await message.reply_text("❌ **pytgcalls غير متاح**")
    
    try:
        await calls.pause_stream(message.chat.id)
        await message.reply_text("⏸️ **تم الإيقاف المؤقت**")
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {str(e)}")

@bot.on_message(filters.command("resume") & (filters.group | filters.channel))
async def resume_cmd(client, message: Message):
    stats['messages'] += 1
    
    if not pytgcalls_available:
        return await message.reply_text("❌ **pytgcalls غير متاح**")
    
    try:
        await calls.resume_stream(message.chat.id)
        await message.reply_text("▶️ **تم الاستئناف**")
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {str(e)}")

@bot.on_message(filters.command("skip") & (filters.group | filters.channel))
async def skip_cmd(client, message: Message):
    stats['messages'] += 1
    
    chat_id = message.chat.id
    
    if chat_id not in currently_playing:
        return await message.reply_text("❌ **لا يوجد شيء قيد التشغيل**")
    
    skipped = currently_playing[chat_id]['title']
    await message.reply_text(f"⏭️ **تخطي:** {skipped}")
    
    await play_next_song(chat_id)

@bot.on_message(filters.command("stop") & (filters.group | filters.channel))
async def stop_cmd(client, message: Message):
    stats['messages'] += 1
    
    chat_id = message.chat.id
    
    try:
        if pytgcalls_available and calls:
            await calls.leave_group_call(chat_id)
        
        count = len(music_queue.get(chat_id, []))
        
        if chat_id in music_queue:
            music_queue[chat_id] = []
        if chat_id in currently_playing:
            del currently_playing[chat_id]
        
        await message.reply_text(f"⏹️ **تم الإيقاف!**\nحذف {count} أغنية")
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {str(e)}")

@bot.on_message(filters.command("queue"))
async def queue_cmd(client, message: Message):
    stats['messages'] += 1
    
    chat_id = message.chat.id
    
    text = ""
    
    if chat_id in currently_playing:
        current = currently_playing[chat_id]
        text += f"▶️ **قيد التشغيل:**\n🎵 {current['title']}\n⏱️ {format_duration(current['duration'])}\n\n"
    
    if chat_id in music_queue and music_queue[chat_id]:
        text += "📋 **قائمة الانتظار:**\n\n"
        for i, song in enumerate(music_queue[chat_id][:10], 1):
            text += f"**{i}.** {song['title']}\n⏱️ {format_duration(song['duration'])}\n\n"
        
        if len(music_queue[chat_id]) > 10:
            text += f"\n_...و {len(music_queue[chat_id]) - 10} أخرى_"
        
        text += f"\n**الإجمالي:** {len(music_queue[chat_id])} أغنية"
    else:
        if not text:
            text = "📭 **القائمة فارغة**"
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🗑️ حذف القائمة", callback_data=f"clear_{chat_id}")
    ]])
    
    await message.reply_text(text, reply_markup=keyboard)

@bot.on_message(filters.command("current"))
async def current_cmd(client, message: Message):
    stats['messages'] += 1
    
    chat_id = message.chat.id
    
    if chat_id not in currently_playing:
        return await message.reply_text("❌ **لا يوجد شيء قيد التشغيل**")
    
    song = currently_playing[chat_id]
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎵 YouTube", url=song['webpage_url'])
    ]])
    
    await message.reply_text(
        f"▶️ **قيد التشغيل:**\n\n"
        f"🎵 {song['title']}\n"
        f"👤 {song['uploader']}\n"
        f"⏱️ {format_duration(song['duration'])}\n"
        f"👁️ {format_number(song.get('view_count', 0))} مشاهدة",
        reply_markup=keyboard
    )

@bot.on_message(filters.command("clear"))
async def clear_cmd(client, message: Message):
    stats['messages'] += 1
    
    chat_id = message.chat.id
    
    if chat_id in music_queue and music_queue[chat_id]:
        count = len(music_queue[chat_id])
        music_queue[chat_id] = []
        await message.reply_text(f"🗑️ **تم حذف {count} أغنية من القائمة**")
    else:
        await message.reply_text("📭 **القائمة فارغة بالفعل**")

# Callback handlers
@bot.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    data = callback_query.data
    
    if data == "help":
        await help_cmd(client, callback_query.message)
        await callback_query.answer()
    
    elif data == "stats":
        await stats_cmd(client, callback_query.message)
        await callback_query.answer()
    
    elif data == "about":
        # **تم تحديث الوصف ليعكس اسم المكتبة الصحيح**
        await callback_query.message.edit_text(
            f"ℹ️ **حول البوت**\n\n"
            f"🤖 **الاسم:** Music Bot\n"
            f"📦 **الإصدار:** 2.0.0\n"
            f"🛠️ **المكتبة:** Pyrogram + pytgcalls\n"
            f"🔍 **المحرك:** yt-dlp\n\n"
            f"**الحالة:**\n"
            f"• البوت: ✅ نشط\n"
            f"• UserBot: {'✅ متصل' if userbot_available else '❌ غير متصل'}\n"
            f"• pytgcalls: {'✅ جاهز' if pytgcalls_available else '❌ غير متاح'}\n\n"
            f"تم التطوير بـ ❤️"
        )
        await callback_query.answer()
    
    elif data.startswith("pause_"):
        if pytgcalls_available:
            chat_id = int(data.split("_")[1])
            try:
                await calls.pause_stream(chat_id)
                await callback_query.answer("⏸️ تم الإيقاف المؤقت", show_alert=True)
            except:
                await callback_query.answer("❌ خطأ", show_alert=True)
        else:
            await callback_query.answer("❌ غير متاح", show_alert=True)
    
    elif data.startswith("skip_"):
        chat_id = int(data.split("_")[1])
        if chat_id in currently_playing:
            await play_next_song(chat_id)
            await callback_query.answer("⏭️ تم التخطي", show_alert=True)
        else:
            await callback_query.answer("❌ لا يوجد شيء قيد التشغيل", show_alert=True)
    
    elif data.startswith("stop_"):
        if pytgcalls_available:
            chat_id = int(data.split("_")[1])
            try:
                await calls.leave_group_call(chat_id)
                if chat_id in music_queue:
                    music_queue[chat_id] = []
                if chat_id in currently_playing:
                    del currently_playing[chat_id]
                await callback_query.answer("⏹️ تم الإيقاف", show_alert=True)
            except:
                await callback_query.answer("❌ خطأ", show_alert=True)
        else:
            await callback_query.answer("❌ غير متاح", show_alert=True)
    
    elif data.startswith("clear_"):
        chat_id = int(data.split("_")[1])
        if chat_id in music_queue:
            count = len(music_queue[chat_id])
            music_queue[chat_id] = []
            await callback_query.message.edit_text(f"🗑️ **تم حذف {count} أغنية**")
        await callback_query.answer("تم الحذف!")
    
    else:
        await callback_query.answer()

# Web server
async def health(request):
    return web.Response(text=f"OK")

async def index(request):
    uptime = time.time() - stats['start_time']
    hours = int(uptime // 3600)
    mins = int((uptime % 3600) // 60)
    
    html = f"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Music Bot Dashboard</title>
    <meta http-equiv="refresh" content="30">
    <style>
        *{{margin:0;padding:0;box-sizing:border-box}}
        body{{
            font-family:'Segoe UI',Tahoma,sans-serif;
            background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);
            color:#fff;
            min-height:100vh;
            display:flex;
            justify-content:center;
            align-items:center;
            padding:20px
        }}
        .container{{
            background:rgba(255,255,255,0.15);
            padding:50px;
            border-radius:30px;
            backdrop-filter:blur(20px);
            box-shadow:0 20px 60px rgba(0,0,0,0.5);
            max-width:700px;
            width:100%;
            text-align:center
        }}
        h1{{font-size:4em;margin-bottom:20px}}
        .status{{font-size:2em;color:#4ade80;margin:20px 0;font-weight:bold}}
        .stats{{
            display:grid;
            grid-template-columns:repeat(3,1fr);
            gap:15px;
            margin:30px 0
        }}
        .stat{{
            background:rgba(255,255,255,0.1);
            padding:20px;
            border-radius:15px
        }}
        .stat-number{{font-size:2.5em;font-weight:bold;color:#4ade80}}
        .stat-label{{font-size:0.9em;margin-top:5px;opacity:0.8}}
        .info{{
            background:rgba(255,255,255,0.1);
            padding:15px;
            border-radius:10px;
            margin:10px 0;
            font-size:1.1em
        }}
        a{{
            display:inline-block;
            margin-top:30px;
            padding:18px 40px;
            background:linear-gradient(135deg,#4ade80,#22c55e);
            color:#fff;
            text-decoration:none;
            border-radius:50px;
            font-size:1.4em;
            font-weight:bold;
            transition:transform 0.2s
        }}
    """
    
    # ... (بقية كود index)
    
    # **ملاحظة:** لم يتم تضمين الجزء المتبقي من دالة index لأنه لم يكن موجودًا في الكود الذي قدمته، وتم إيقاف الكود عند السطر الأخير من الـ HTML.
    
    # إذا كنت تحتاج إلى الجزء المتبقي من الدالة، يرجى تزويدي به.
    # بناءً على الكود الذي قدمته، لا يمكن إكماله بشكل صحيح، لذا سأفترض أنك قمت بتضمين الأجزاء الأساسية فقط.
    # سأقوم بتضمين السطر الأخير لدالة index لضمان عدم وجود خطأ نحوي (syntax error).
    
    stats_html = f"""
    <div class="stats">
        <div class="stat"><div class="stat-number">{len(currently_playing)}</div><div class="stat-label">قيد التشغيل</div></div>
        <div class="stat"><div class="stat-number">{len(music_queue)}</div><div class="stat-label">قوائم انتظار نشطة</div></div>
        <div class="stat"><div class="stat-number">{stats['songs_played']}</div><div class="stat-label">الأغاني المشغلة</div></div>
        <div class="stat"><div class="stat-number">{len(stats['users'])}</div><div class="stat-label">إجمالي المستخدمين</div></div>
        <div class="stat"><div class="stat-number">{stats['messages']}</div><div class="stat-label">إجمالي الرسائل</div></div>
        <div class="stat"><div class="stat-number">{hours}h {mins}m</div><div class="stat-label">وقت التشغيل</div></div>
    </div>
    <div class="info">UserBot Status: {'✅ Connected' if userbot_available else '❌ Disconnected'}</div>
    <div class="info">pytgcalls Status: {'✅ Ready' if pytgcalls_available else '❌ Unavailable'}</div>
    """
    
    return web.Response(text=html + """
    </style>
</head>
<body>
    <div class="container">
        <h1>Music Bot</h1>
        <div class="status">✅ Service is Running</div>
        """ + stats_html + """
        <a href="https://t.me/AtheerAlsalafBot" target="_blank">Start Bot on Telegram</a>
    </div>
</body>
</html>
""")

# Main entry point
async def start_bot_and_server():
    global bot_username
    
    # Get bot info
    try:
        me = await bot.get_me()
        bot_username = me.username
        logger.info(f"✅ Bot: @{bot_username}")
        logger.info(f"✅ Bot ID: {me.id}")
    except Exception as e:
        logger.error(f"❌ Bot connection error: {e}")
        return
    
    # Get userbot info
    if userbot_available:
        try:
            user_me = await userbot.get_me()
            logger.info(f"✅ UserBot: {user_me.first_name}")
        except Exception as e:
            logger.error(f"❌ UserBot connection error: {e}")
            
    if userbot_available and pytgcalls_available and calls:
        try:
            await calls.start()
            logger.info("✅ pytgcalls started")
        except Exception as e:
            logger.error(f"❌ pytgcalls start error: {e}")

    logger.info("============================================================")
    logger.info("🎵 MUSIC BOT WITH PYTGCALLS")
    logger.info("============================================================")
    logger.info(f"✅ Bot: @{bot_username}")
    logger.info(f"✅ Bot ID: {me.id}")
    
    if userbot_available:
        logger.info(f"✅ UserBot: {user_me.first_name if 'user_me' in locals() else 'configured'}")
        logger.info(f"🤖 Auto-join: ENABLED")
    else:
        logger.warning("⚠️ UserBot: NOT AVAILABLE")
    
    logger.warning(f"⚠️ pytgcalls: {'NOT AVAILABLE' if not pytgcalls_available else 'READY'}")
    
    # Start web server (Render requirement)
    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_get('/health', health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"✅ Web server on port {PORT}")

    logger.info("============================================================")
    logger.info("✅ BOT READY!")
    logger.info(f"🔗 https://t.me/{bot_username}")
    logger.info("============================================================")

    # Start polling
    await bot.run_until_disconnected()

if __name__ == "__main__":
    try:
        bot.run(start_bot_and_server())
    except Exception as e:
        logger.error(f"Fatal error during startup: {e}")
