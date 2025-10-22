"""Start and help commands."""

from pyrogram import Client, filters
from pyrogram.types import Message
from bot.helpers.localization import get_text, localization
from bot.helpers.keyboards import Keyboards

@Client.on_message(filters.command(["start", "help"]) & filters.private)
async def start_command(client: Client, message: Message):
    """Handle /start and /help commands."""
    user_id = message.from_user.id
    
    await message.reply(
        get_text(user_id, "start_message"),
        reply_markup=Keyboards.start_buttons(user_id)
    )

@Client.on_message(filters.command("language"))
async def language_command(client: Client, message: Message):
    """Handle /language command."""
    await message.reply(
        get_text(message.from_user.id, "choose_language"),
        reply_markup=Keyboards.language_buttons()
    )
