"""إعدادات التطبيق من متغيرات البيئة."""

import os
import sys
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# تحميل متغيرات البيئة من ملف .env
load_dotenv()

class _Config:
    """كلاس الإعدادات."""
    
    def __init__(self):
        # إعدادات Telegram API
        self.API_ID = int(os.getenv("API_ID", "0"))
        self.API_HASH = os.getenv("API_HASH", "")
        self.BOT_TOKEN = os.getenv("BOT_TOKEN", "")
        self.SESSION_STRING = os.getenv("SESSION_STRING", "")
        
        # إعدادات المساعد
        self.ASSISTANT_USERNAME = os.getenv("ASSISTANT_USERNAME", "vcmplayer")
        
        # إعدادات التطبيق
        self.DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "downloads"))
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.PORT = int(os.getenv("PORT", "8080"))
        self.STATE_BACKEND = os.getenv("STATE_BACKEND", "tinydb")
        
        # إعدادات اختيارية
        self.MONGODB_URI = os.getenv("MONGODB_URI")
        
        # إعدادات وقت التشغيل
        self.RATE_LIMIT_SECONDS = 3  # التأخير بين الأوامر
        self.PROGRESS_UPDATE_INTERVAL = 10  # تحديث شريط التقدم كل 10 ثواني
        self.STATE_SAVE_INTERVAL = 15  # حفظ الحالة كل 15 ثانية
        self.CLEANUP_INTERVAL = 300  # تنظيف الملفات كل 5 دقائق
        self.MAX_QUEUE_SIZE = 50  # الحد الأقصى للقائمة
        self.MAX_DOWNLOAD_SIZE = 100 * 1024 * 1024  # 100 ميجابايت
    
    def validate(self):
        """التحقق من الإعدادات المطلوبة."""
        errors = []
        
        if not self.API_ID or self.API_ID == 0:
            errors.append("API_ID مطلوب")
        if not self.API_HASH:
            errors.append("API_HASH مطلوب")
        if not self.BOT_TOKEN:
            errors.append("BOT_TOKEN مطلوب")
        if not self.SESSION_STRING:
            errors.append("SESSION_STRING مطلوب")
            
        if errors:
            print("أخطاء في الإعدادات:")
            for error in errors:
                print(f"  - {error}")
            sys.exit(1)
            
        # إنشاء مجلد التحميلات
        self.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# إنشاء نسخة واحدة من الإعدادات
config = _Config()
