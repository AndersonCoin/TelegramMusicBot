"""Configuration management with environment variables."""

import os
import sys
from pathlib import Path
from typing import Literal
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Application configuration."""
    
    # Telegram API
    API_ID: int = int(os.getenv("API_ID", "0"))
    API_HASH: str = os.getenv("API_HASH", "")
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    SESSION_STRING: str = os.getenv("SESSION_STRING", "")
    
    # Assistant
    ASSISTANT_USERNAME: str = os.getenv("ASSISTANT_USERNAME", "vcmplayer")
    
    # Application
    DOWNLOAD_DIR: Path = Path(os.getenv("DOWNLOAD_DIR", "downloads"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    PORT: int = int(os.getenv("PORT", "8080"))
    STATE_BACKEND: Literal["tinydb", "sqlite"] = os.getenv("STATE_BACKEND", "tinydb")
    
    # Limits
    MAX_QUEUE_SIZE: int = 50
    PROGRESS_UPDATE_INTERVAL: int = 10  # seconds
    STATE_SAVE_INTERVAL: int = 15  # seconds
    RATE_LIMIT_SECONDS: int = 3  # seconds between plays per user
    
    @classmethod
    def validate(cls) -> None:
        """Validate required configuration."""
        errors = []
        
        if not cls.API_ID or cls.API_ID == 0:
            errors.append("API_ID is required")
        if not cls.API_HASH:
            errors.append("API_HASH is required")
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN is required")
        if not cls.SESSION_STRING:
            errors.append("SESSION_STRING is required")
            
        if errors:
            print("Configuration errors:")
            for error in errors:
                print(f"  - {error}")
            sys.exit(1)
            
        # Create download directory
        cls.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Validate on import
Config.validate()
