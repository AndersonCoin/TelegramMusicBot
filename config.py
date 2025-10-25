import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram API credentials
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    # Bot settings
    OWNER_ID = int(os.getenv("OWNER_ID", 0))
    SUPPORT_GROUP = os.getenv("SUPPORT_GROUP", "")
    
    # Music settings
    DURATION_LIMIT = int(os.getenv("DURATION_LIMIT", 300))  # 5 minutes
    QUEUE_LIMIT = int(os.getenv("QUEUE_LIMIT", 10))
    
    # Admin list
    SUDO_USERS = list(map(int, os.getenv("SUDO_USERS", "").split()))
