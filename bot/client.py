import logging
from pyrogram import Client
from pytgcalls import PyTgCalls
from config import Config

logger = logging.getLogger(__name__)

# ✅ عرّف نسخة البوت هنا باسم 'app'
# هذا هو المتغير الذي سيتم استيراده
app = Client(
    name="MusicBot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    workdir=str(Config.BASE_DIR),
    plugins=dict(root="bot/plugins")
)

# عرّف نسخة المساعد
user_app = Client(
    name="UserBot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    session_string=Config.SESSION_STRING,
    workdir=str(Config.BASE_DIR)
)

# عرّف نسخة PyTgCalls
pytgcalls = PyTgCalls(user_app)

logger.info("Clients initialized.")
