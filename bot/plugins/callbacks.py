"""Callback query handlers."""

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery
from bot.core.queue import queue_manager
from bot.helpers.localization import get_text, localization
from bot.helpers.keyboards import Keyboards
from bot.helpers.formatting import format_queue_list, format_duration, create_progress_bar

@Client.on_callback_query(filters.regex(r"^lang_"))
async def language_callback(client: Client, callback: CallbackQuery):
    """Handle language selection."""
    lang = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    localization.set_language(user_id, lang)
    
    await callback.answer(
        get_text(user_id, "language_changed"),
        show_alert=True
    )
    
    # Update message
    await callback.message.edit(
        get_text(user_id, "start_message"),
        reply_markup=Keyboards.start_buttons(user_id)
    )

@Client.on_callback_query(filters.regex(r"^player_"))
async def player_callback(client: Client, callback: CallbackQuery):
    """Handle player control callbacks."""
    data = callback.data.split(":")
    action = data[0].split("_")[1]
    chat_id = int(data[1]) if len(data) > 1 else callback.message.chat.id
    user_id = callback.from_user.id
    
    # Check admin
    try:
        member = await callback.message.chat.get_member(user_id)
        if not member.privileges:
            await callback.answer(get_text(user_id, "only_admins"), show_alert=True)
            return
    except:
        pass
    
    # Handle action
    if action == "pause":
        if await client.music.player.pause(chat_id):
            await callback.answer(get_text(user_id, "paused"))
            # Update buttons
            await callback.message.edit_reply_markup(
                Keyboards.player_controls(chat_id, is_paused=True)
            )
    
    elif action == "play":
        if await client.music.player.resume(chat_id):
            await callback.answer(get_text(user_id, "resumed"))
            # Update buttons
            await callback.message.edit_reply_markup(
                Keyboards.player_controls(chat_id, is_paused=False)
            )
    
    elif action == "skip":
        next_track = await client.music.player.skip(chat_id)
        if next_track:
            await callback.answer(get_text(user_id, "skipped"))
            # Update now playing message
            text = get_text(
                user_id,
                "now_playing",
                title=next_track.title,
                duration=format_duration(next_track.duration),
                requester=next_track.requester_name,
                progress_bar=create_progress_bar(0, next_track.duration),
                elapsed=format_duration(0),
                total=format_duration(next_track.duration)
            )
            await callback.message.edit(
                text,
                reply_markup=Keyboards.player_controls(chat_id)
            )
        else:
            await callback.answer(get_text(user_id, "stopped"))
            await callback.message.delete()
    
    elif action == "stop":
        if await client.music.player.stop(chat_id):
            await callback.answer(get_text(user_id, "stopped"))
            await callback.message.delete()
    
    elif action == "settings":
        await callback.message.edit_reply_markup(
            Keyboards.settings_menu(chat_id)
        )

@Client.on_callback_query(filters.regex(r"^queue_"))
async def queue_callback(client: Client, callback: CallbackQuery):
    """Handle queue navigation callbacks."""
    data = callback.data.split(":")
    action = data[0].split("_")[1]
    chat_id = int(data[1])
    page = int(data[2]) if len(data) > 2 else 1
    user_id = callback.from_user.id
    
    # Get queue
    queue = queue_manager.get_queue(chat_id)
    
    if not queue.tracks:
        await callback.answer(get_text(user_id, "queue_empty"))
        return
    
    if action in ["open", "nav"]:
        # Format queue
        text, total_pages = format_queue_list(queue.tracks, page=page)
        
        # Update message
        await callback.message.edit(
            get_text(user_id, "queue_title", page=page, total_pages=total_pages) + "\n\n" + text,
            reply_markup=Keyboards.queue_navigation(chat_id, page, total_pages)
        )

@Client.on_callback_query(filters.regex(r"^back_to_player"))
async def back_to_player_callback(client: Client, callback: CallbackQuery):
    """Handle back to player callback."""
    chat_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    # Get current track
    info = client.music.player.active_chats.get(chat_id)
    if not info:
        await callback.answer(get_text(user_id, "not_playing"))
        return
    
    track = info["track"]
    
    # Update to now playing
    text = get_text(
        user_id,
        "now_playing",
        title=track.title,
        duration=format_duration(track.duration),
        requester=track.requester_name,
        progress_bar=create_progress_bar(info["position"], track.duration),
        elapsed=format_duration(info["position"]),
        total=format_duration(track.duration)
    )
    
    await callback.message.edit(
        text,
        reply_markup=Keyboards.player_controls(chat_id, is_paused=info["paused"])
    )
