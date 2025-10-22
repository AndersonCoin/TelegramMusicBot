"""Start and help commands."""

from pyrogram import Client, filters
from pyrogram.types import Message

from bot.helpers.localization import get_text
from bot.helpers.keyboards import keyboards


@Client.on_message(filters.command(["start", "help"]) & filters.group)
async def start_group(client: Client, message: Message):
    """Handle /start and /help in groups."""
    await message.reply_text(
        get_text(message.chat, "help"),
        reply_markup=keyboards.language_menu()
    )


@Client.on_message(filters.command(["start", "help"]) & filters.private)
async def start_private(client: Client, message: Message):
    """Handle /start and /help in private."""
    await message.reply_text(
        get_text(message.from_user, "welcome"),
        reply_markup=keyboards.language_menu()
    )


@Client.on_message(filters.command("language"))
async def language_command(client: Client, message: Message):
    """Handle /language command."""
    await message.reply_text(
        get_text(message.chat if message.chat else message.from_user, "language_menu"),
        reply_markup=keyboards.language_menu()
    )
