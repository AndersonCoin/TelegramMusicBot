"""Inline keyboard builders."""

from typing import Optional, List
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.helpers.localization import get_text

class Keyboards:
    """Keyboard builder utilities."""
    
    @staticmethod
    def start_buttons(user_id: int) -> InlineKeyboardMarkup:
        """Start command buttons."""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    get_text(user_id, "help_button"),
                    callback_data="help"
                ),
                InlineKeyboardButton(
                    get_text(user_id, "language_button"),
                    callback_data="language_menu"
                )
            ]
        ])
    
    @staticmethod
    def language_buttons() -> InlineKeyboardMarkup:
        """Language selection buttons."""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("English", callback_data="lang_en"),
                InlineKeyboardButton("العربية", callback_data="lang_ar")
            ]
        ])
    
    @staticmethod
    def player_controls(chat_id: int, is_paused: bool = False) -> InlineKeyboardMarkup:
        """Now playing control buttons."""
        pause_play_btn = InlineKeyboardButton(
            "▶️ Play" if is_paused else "⏸️ Pause",
            callback_data=f"player_{'play' if is_paused else 'pause'}:{chat_id}"
        )
        
        return InlineKeyboardMarkup([
            [
                pause_play_btn,
                InlineKeyboardButton("⏭️ Skip", callback_data=f"player_skip:{chat_id}"),
                InlineKeyboardButton("⏹️ Stop", callback_data=f"player_stop:{chat_id}")
            ],
            [
                InlineKeyboardButton("📃 Queue", callback_data=f"queue_open:{chat_id}:1"),
                InlineKeyboardButton("⚙️ Settings", callback_data=f"player_settings:{chat_id}")
            ]
        ])
    
    @staticmethod
    def queue_navigation(chat_id: int, page: int, total_pages: int) -> InlineKeyboardMarkup:
        """Queue navigation buttons."""
        buttons = []
        
        # Navigation row
        nav_row = []
        if page > 1:
            nav_row.append(
                InlineKeyboardButton("◀️ Previous", callback_data=f"queue_nav:{chat_id}:{page-1}")
            )
        nav_row.append(
            InlineKeyboardButton("🔄 Refresh", callback_data=f"queue_nav:{chat_id}:{page}")
        )
        if page < total_pages:
            nav_row.append(
                InlineKeyboardButton("Next ▶️", callback_data=f"queue_nav:{chat_id}:{page+1}")
            )
        
        if nav_row:
            buttons.append(nav_row)
        
        # Back button
        buttons.append([
            InlineKeyboardButton("🔙 Back to Player", callback_data=f"back_to_player:{chat_id}")
        ])
        
        return InlineKeyboardMarkup(buttons)
    
    @staticmethod
    def settings_menu(chat_id: int) -> InlineKeyboardMarkup:
        """Settings menu buttons."""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔊 Vol+", callback_data=f"volume_up:{chat_id}"),
                InlineKeyboardButton("🔉 Vol-", callback_data=f"volume_down:{chat_id}")
            ],
            [
                InlineKeyboardButton("🔁 Loop Track", callback_data=f"loop_toggle:{chat_id}"),
                InlineKeyboardButton("🔀 Shuffle", callback_data=f"shuffle:{chat_id}")
            ],
            [
                InlineKeyboardButton("🔙 Back to Player", callback_data=f"back_to_player:{chat_id}")
            ]
        ])
