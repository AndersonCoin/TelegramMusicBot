import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_ID = int(os.getenv("API_ID", 0))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    SESSION_STRING = os.getenv("SESSION_STRING")
    ASSISTANT_USERNAME = os.getenv("ASSISTANT_USERNAME")

    BASE_DIR = Path(__file__).parent
    DOWNLOAD_DIR = BASE_DIR / os.getenv("DOWNLOAD_DIR", "downloads")
    LOG_DIR = BASE_DIR / "logs"

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    PORT = int(os.getenv("PORT", 8080))
    STATE_BACKEND = os.getenv("STATE_BACKEND", "tinydb")

    @classmethod
    def validate(cls):
        errors = []
        if not cls.API_ID: errors.append("API_ID")
        if not cls.API_HASH: errors.append("API_HASH")
        if not cls.BOT_TOKEN: errors.append("BOT_TOKEN")
        if not cls.SESSION_STRING: errors.append("SESSION_STRING")
        if not cls.ASSISTANT_USERNAME: errors.append("ASSISTANT_USERNAME")
        
        if errors:
            raise ValueError(f"Missing required config vars: {', '.join(errors)}")

        cls.DOWNLOAD_DIR.mkdir(exist_ok=True)
        cls.LOG_DIR.mkdir(exist_ok=True)
        return True
