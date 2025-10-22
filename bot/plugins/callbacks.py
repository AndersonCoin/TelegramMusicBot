import logging
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery
from bot.helpers.localization import get_text, set_language
from bot.helpers.keyboards import get_player_keyboard, get_queue_keyboard, get_language_keyboard
from bot.core.player import player
from bot.core.queue import queue_manager

logger = logging.getLogger(__name__)

@Client.on_callback_query()
async def callback_handler(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data
    
    # Language callbacks
    if data.startswith("lang_"):
        lang_code = data.split("_")[1]
        if set_language(user_id, lang_code):
            await callback.message.edit_text(
                get_text(user_id, "help_text"),
                reply_markup=get_language_keyboard()
            )
            await callback.answer(get_text(user_id, "lang_changed"))
        return

    # Player callbacks
    chat_id_str = data.split(":")[-1]
    if not chat_id_str.isdigit():
        await callback.answer("Invalid callback data.", show_alert=True)
        return
    
    chat_id = int(chat_id_str)
    
    # Admin check for controls
    is_admin = False
    try:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status in ["creator", "administrator"]:
            is_admin = True
    except Exception as e:
        logger.error(f"Callback permission check error: {e}")
    
    if not is_admin and any(data.startswith(p) for p in ["player_pause", "player_play", "player_skip", "player_stop"]):
        await callback.answer(get_text(user_id, "admin_only"), show_alert=True)
        return

    # Routing
    if data.startswith("player_pause"):
        await player.pause(chat_id)
        await callback.answer(get_text(user_id, "paused"))
        await callback.message.edit_reply_markup(get_player_keyboard(chat_id, is_paused=True))

    elif data.startswith("player_play"):
        await player.resume(chat_id)
        await callback.answer(get_text(user_id, "resumed"))
        await callback.message.edit_reply_markup(get_player_keyboard(chat_id, is_paused=False))

    elif data.startswith("player_skip"):
        next_track = await player.skip(chat_id)
        if next_track:
            await callback.answer(get_text(user_id, "skipped"))
        else:
            await callback.answer(get_text(user_id, "queue_empty"), show_alert=True)
            await callback.message.delete()
    
    elif data.startswith("player_stop"):
        await player.stop(chat_id)
        await callback.answer(get_text(user_id, "stopped"))
        await callback.message.delete()

    elif data.startswith("queue_open") or data.startswith("queue_nav"):
        _, _, page_str = data.split(":")
        page = int(page_str)

        queue = queue_manager.get_queue(chat_id)
        upcoming = queue.queue
        total_pages = max(1, (len(upcoming) + 4) // 5)
        
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * 5
        end_idx = start_idx + 5
        page_items = upcoming[start_idx:end_idx]

        text = get_text(user_id, "queue_title") + "\n"
        if not page_items:
            text += get_text(user_id, "queue_empty")
        else:
            for i, track in enumerate(page_items, start=start_idx + 1):
                text += f"{i}. {track.title}\n"
        
        await callback.message.edit_text(text, reply_markup=get_queue_keyboard(chat_id, page, total_pages))

    elif data.startswith("player_view"):
        queue = queue_manager.get_queue(chat_id)
        track = queue.current_track
        if track:
            # Refresh the now playing message (progress bar will handle the text)
            await player.start_progress_updater(chat_id, callback.message.id)
            await callback.answer()
        else:
            await callback.message.edit_text(get_text(user_id, "queue_empty"))
            await callback.answer()
