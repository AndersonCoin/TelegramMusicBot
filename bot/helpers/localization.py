"""Localization system."""

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

class Localization:
    """Handles multi-language support."""
    
    def __init__(self):
        self.translations: Dict[str, Dict] = {}
        self.user_languages: Dict[int, str] = {}
        self.default_language = "en"
        self._load_translations()
    
    def _load_translations(self):
        """Load all translation files."""
        locales_dir = Path("locales")
        
        for file_path in locales_dir.glob("*.json"):
            lang_code = file_path.stem
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    self.translations[lang_code] = json.load(f)
                logger.info(f"Loaded language: {lang_code}")
            except Exception as e:
                logger.error(f"Failed to load {lang_code}: {e}")
    
    def get_text(
        self,
        user_or_chat_id: int,
        key: str,
        **kwargs
    ) -> str:
        """Get translated text for user/chat."""
        lang = self.user_languages.get(user_or_chat_id, self.default_language)
        
        # Get translation
        text = self.translations.get(lang, {}).get(key)
        
        # Fallback to English
        if not text:
            text = self.translations.get(self.default_language, {}).get(key, key)
        
        # Format with kwargs
        try:
            return text.format(**kwargs) if kwargs else text
        except:
            return text
    
    def set_language(self, user_or_chat_id: int, language: str):
        """Set language for user/chat."""
        if language in self.translations:
            self.user_languages[user_or_chat_id] = language
            return True
        return False
    
    def get_language(self, user_or_chat_id: int) -> str:
        """Get current language for user/chat."""
        return self.user_languages.get(user_or_chat_id, self.default_language)

# Global instance
localization = Localization()

# Helper function
def get_text(user_or_chat_id: int, key: str, **kwargs) -> str:
    """Quick access to get_text."""
    return localization.get_text(user_or_chat_id, key, **kwargs)
