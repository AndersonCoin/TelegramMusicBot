from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_player_keyboard(chat_id: int, is_paused: bool = False) -> InlineKeyboardMarkup:
    play_pause_button = InlineKeyboardButton(
        "▶️ Play", callback_data=f"player_play:{chat_id}"
    ) if is_paused else InlineKeyboardButton(
        "⏸️ Pause", callback_data=f"player_pause:{chat_id}"
    )

    return InlineKeyboardMarkup([
        [
            play_pause_button,
            InlineKeyboardButton("⏭️ Skip", callback_data=f"player_skip:{chat_id}"),
            InlineKeyboardButton("⏹️ Stop", callback_data=f"player_stop:{chat_id}")
        ],
        [
            InlineKeyboardButton("📃 Queue", callback_data=f"queue_open:{chat_id}:1")
        ]
    ])

def get_queue_keyboard(chat_id: int, page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"queue_nav:{chat_id}:{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"Page {page}/{total_pages}", callback_data="noop"))
    
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"queue_nav:{chat_id}:{page+1}"))
    
    return InlineKeyboardMarkup([
        nav_buttons,
        [InlineKeyboardButton("🔙 Back to Player", callback_data=f"player_view:{chat_id}")]
    ])

def get_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
            InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar")
        ]
    ])
