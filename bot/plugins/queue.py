"""Queue management commands."""

from pyrogram import Client, filters
from pyrogram.types import Message
from bot.core.queue import queue_manager
from bot.helpers.localization import get_text
from bot.helpers.formatting import format_queue_list
from bot.helpers.keyboards import Keyboards

@Client.on_message(filters.command("queue") & filters.group)
async def queue_command(client: Client, message: Message):
    """Handle /queue command."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Get queue
    queue = queue_manager.get_queue(chat_id)
    
    if not queue.tracks:
        await message.reply(get_text(user_id, "queue_empty"))
        return
    
    # Format queue
    text, total_pages = format_queue_list(queue.tracks, page=1)
    
    if not text:
        await message.reply(get_text(user_id, "queue_empty"))
        return
    
    # Send queue message
    await message.reply(
        get_text(user_id, "queue_title", page=1, total_pages=total_pages) + "\n\n" + text,
        reply_markup=Keyboards.queue_navigation(chat_id, 1, total_pages)
    )
