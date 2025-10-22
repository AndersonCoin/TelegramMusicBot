"""Configuration module for environment variables and validation."""

import os
import sys
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class _Config:
    """Application configuration from environment variables."""
    
    def __init__(self):
        # Telegram API
        self.API_ID = int(os.getenv("API_ID", "0"))
        self.API_HASH = os.getenv("API_HASH", "")
        self.BOT_TOKEN = os.getenv("BOT_TOKEN", "")
        self.SESSION_STRING = os.getenv("SESSION_STRING", "")
        
        # Assistant
        self.ASSISTANT_USERNAME = os.getenv("ASSISTANT_USERNAME", "vcmplayer")
        
        # Application
        self.DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "downloads"))
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.PORT = int(os.getenv("PORT", "8080"))
        self.STATE_BACKEND = os.getenv("STATE_BACKEND", "tinydb")
        
        # Optional
        self.MONGODB_URI = os.getenv("MONGODB_URI")
        
        # Runtime
        self.RATE_LIMIT_SECONDS = 3
        self.PROGRESS_UPDATE_INTERVAL = 10
        self.STATE_SAVE_INTERVAL = 15
        self.CLEANUP_INTERVAL = 300
        self.MAX_QUEUE_SIZE = 50
        self.MAX_DOWNLOAD_SIZE = 100 * 1024 * 1024
    
    def validate(self):
        """Validate required configuration."""
        errors = []
        
        if not self.API_ID or self.API_ID == 0:
            errors.append("API_ID is required")
        if not self.API_HASH:
            errors.append("API_HASH is required")
        if not self.BOT_TOKEN:
            errors.append("BOT_TOKEN is required")
        if not self.SESSION_STRING:
            errors.append("SESSION_STRING is required")
            
        if errors:
            print("Configuration errors:")
            for error in errors:
                print(f"  - {error}")
            sys.exit(1)
            
        # Create download directory
        self.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# هذا السطر المهم - إنشاء متغير config
config = _Config()
