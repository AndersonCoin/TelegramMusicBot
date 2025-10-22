"""Queue management commands."""

from pyrogram import Client, filters
from pyrogram.types import Message

from bot.core.queue import queue_manager
from bot.helpers.formatting import formatting
from bot.helpers.keyboards import keyboards
from bot.helpers.localization import get_text


@Client.on_message(filters.command("queue") & filters.group)
async def queue_command(client: Client, message: Message):
    """Handle /queue command."""
    chat_id = message.chat.id
    queue = queue_manager.get_queue(chat_id)
    
    if queue.is_empty:
        await message.reply_text(get_text(message.chat, "queue_empty"))
        return
    
    # Get first page
    tracks, total_pages = queue.get_page(1, 10)
    
    # Build queue text
    text = get_text(message.chat, "queue_title", page=1, total_pages=total_pages) + "\n\n"
    
    for i, track in enumerate(tracks, 1):
        text += get_text(
            message.chat,
            "queue_item",
            index=i,
            title=track.title,
            duration=formatting.duration(track.duration)
        ) + "\n"
    
    await message.reply_text(
        text,
        reply_markup=keyboards.queue_navigation(chat_id, 1, total_pages)
    )
