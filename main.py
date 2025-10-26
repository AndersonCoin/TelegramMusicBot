import os
import logging
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

# تحميل متغيرات البيئة
load_dotenv()

# إعداد السجلات
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# الحصول على المتغيرات
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# التحقق من وجود المتغيرات
if not API_ID or not API_HASH or not BOT_TOKEN:
    logger.error("❌ Missing environment variables!")
    logger.error("Please set API_ID, API_HASH, and BOT_TOKEN")
    exit(1)

# إنشاء البوت
try:
    app = Client(
        "MusicBot",
        api_id=int(API_ID),
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        in_memory=True
    )
    logger.info("✅ Bot client created successfully")
except Exception as e:
    logger.error(f"❌ Failed to create bot: {e}")
    exit(1)

# قاعدة بيانات مؤقتة
music_queue = {}
active_chats = set()

# ==================== الأوامر ====================

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """أمر البداية"""
    user_name = message.from_user.first_name
    bot_username = (await client.get_me()).username
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ أضفني لمجموعتك", 
                url=f"https://t.me/{bot_username}?startgroup=true"),
        ],
        [
            InlineKeyboardButton("📚 الأوامر", callback_data="help"),
            InlineKeyboardButton("💡 الدعم", url="https://t.me/your_support")
        ]
    ])
    
    welcome_text = f"""
🎵 **مرحباً {user_name}!**

أنا بوت تشغيل الموسيقى في المجموعات 🎶

**المميزات:**
✅ تشغيل الموسيقى من YouTube
✅ التحكم في التشغيل
✅ قائمة انتظار الأغاني
✅ البحث عن الأغاني

**استخدم /help لرؤية جميع الأوامر**
"""
    
    await message.reply_text(
        welcome_text,
        reply_markup=keyboard
    )
    logger.info(f"User {message.from_user.id} started the bot")

@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    """أمر المساعدة"""
    help_text = """
📚 **قائمة الأوامر:**

**🎵 أوامر الموسيقى:**
• /play [اسم الأغنية] - تشغيل أغنية
• /pause - إيقاف مؤقت
• /resume - استئناف التشغيل
• /skip - تخطي الأغنية
• /stop - إيقاف التشغيل
• /queue - عرض قائمة الانتظار

**⚙️ أوامر عامة:**
• /start - بدء البوت
• /help - عرض المساعدة
• /ping - فحص حالة البوت
• /stats - إحصائيات البوت

**👨‍💻 للمشرفين:**
• /volume [1-100] - تغيير الصوت
• /mute - كتم الصوت
• /unmute - إلغاء الكتم
"""
    await message.reply_text(help_text)
    logger.info(f"User {message.from_user.id} requested help")

@app.on_message(filters.command("ping"))
async def 
