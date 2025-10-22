from pyrogram import Client, filters
from pyrogram.types import Message
from bot.helpers.decorators import group_only
from bot.helpers.localization import get_text
from bot.helpers.keyboards import get_queue_keyboard
from bot.core.queue import queue_manager

ITEMS_PER_PAGE = 5

@Client.on_message(filters.command("queue") & filters.group)
@group_only
async def queue_command(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    queue = queue_manager.get_queue(chat_id)
    current = queue.current_track
    upcoming = queue.queue

    if not current and not upcoming:
        await message.reply(get_text(user_id, "queue_empty"))
        return
    
    total_pages = (len(upcoming) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    total_pages = max(total_pages, 1) # Ensure at least one page
    
    text = ""
    if current:
        text += get_text(user_id, "now_playing_title") + f"\n- {current.title}\n\n"
    
    if upcoming:
        text += get_text(user_id, "queue_title") + "\n"
        page_items = upcoming[:ITEMS_PER_PAGE]
        for i, track in enumerate(page_items, 1):
            text += f"{i}. {track.title}\n"
    
    await message.reply(text, reply_markup=get_queue_keyboard(chat_id, 1, total_pages))
