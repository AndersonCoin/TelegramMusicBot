from pyrogram import Client, filters
from pyrogram.types import Message
from bot.helpers.localization import get_text, set_language
from bot.helpers.keyboards import get_language_keyboard

@Client.on_message(filters.command(["start", "help"]))
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    await message.reply_text(
        get_text(user_id, "help_text"),
        reply_markup=get_language_keyboard()
    )

@Client.on_message(filters.command("language"))
async def language_command(client: Client, message: Message):
    await message.reply_text(
        "Please choose a language:",
        reply_markup=get_language_keyboard()
    )
