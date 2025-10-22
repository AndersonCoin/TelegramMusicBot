import json
from config import Config
from bot.persistence.storage import language_storage

_translations = {}
_default_lang = "en"

def load_translations():
    for lang_file in Config.BASE_DIR.joinpath("locales").glob("*.json"):
        lang_code = lang_file.stem
        with open(lang_file, "r", encoding="utf-8") as f:
            _translations[lang_code] = json.load(f)

def get_text(chat_or_user_id, key, **kwargs):
    lang = language_storage.get(str(chat_or_user_id)) or _default_lang
    
    text = _translations.get(lang, {}).get(key)
    if text is None:
        # Fallback to English
        text = _translations.get(_default_lang, {}).get(key, f"_{key}_")
    
    return text.format(**kwargs)

def set_language(chat_or_user_id, lang_code):
    if lang_code in _translations:
        language_storage.set(str(chat_or_user_id), lang_code)
        return True
    return False

# Load translations on startup
load_translations()
