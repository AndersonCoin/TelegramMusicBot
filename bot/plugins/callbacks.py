"""Callback query handlers."""

import logging

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery

from bot.core.player import player
from bot.core.queue import queue_manager
from bot.helpers.formatting import formatting
from bot.helpers.keyboards import keyboards
from bot.helpers.localization import i18n, get_text

logger = logging.getLogger(__name__)


@Client.on_callback_query(filters.regex(r"^player_"))
async def player_callbacks(client: Client, callback: CallbackQuery):
    """Handle player control callbacks."""
    data = callback.data.split(":")
    action = data[0].replace("player_", "")
    chat_id = int(data[1])
    
    # Check if user is admin
    member = await callback.message.chat.get_member(callback.from_user.id)
    if not member.privileges:
        await callback.answer(
            get_text(callback.from_user, "admin_only"),
            show_alert=True
        )
        return
    
    if action == "pause":
        if player and await player.pause(chat_id):
            await callback.answer(get_text(callback.from_user, "paused"))
            # Update keyboard
            await callback.edit_message_reply_markup(
                keyboards.player_controls(chat_id, is_paused=True)
            )
    
    elif action == "play":
        if player and await player.resume(chat_id):
            await callback.answer(get_text(callback.from_user, "resumed"))
            # Update keyboard
            await callback.edit_message_reply_markup(
                keyboards.player_controls(chat_id, is_paused=False)
            )
    
    elif action == "skip":
        if player:
            next_track = await player.skip(chat_id)
            if next_track:
                await callback.answer(get_text(callback.from_user, "skipped"))
            else:
                await callback.answer(get_text(callback.from_user, "queue_empty"))
    
    elif action == "stop":
        if player and await player.stop(chat_id):
            await callback.answer(get_text(callback.from_user, "stopped"))
            await callback.message.delete()
    
    elif action == "settings":
        await callback.edit_message_reply_markup(
            keyboards.settings_menu(chat_id)
        )


@Client.on_callback_query(filters.regex(r"^queue_"))
async def queue_callbacks(client: Client, callback: CallbackQuery):
    """Handle queue navigation callbacks."""
    data = callback.data.split(":")
    action = data[0].replace("queue_", "")
    chat_id = int(data[1])
    
    if action == "open":
        page = int(data[2]) if len(data) > 2 else 1
        queue = queue_manager.get_queue(chat_id)
        
        if queue.is_empty:
            await callback.answer(get_text(callback.from_user, "queue_empty"))
            return
        
        tracks, total_pages = queue.get_page(page, 10)
        
        text = get_text(callback.from_user, "queue_title", page=page, total_pages=total_pages) + "\n\n"
        
        for i, track in enumerate(tracks, (page - 1) * 10 + 1):
            text += get_text(
                callback.from_user,
                "queue_item",
                index=i,
                title=track.title,
                duration=formatting.duration(track.duration)
            ) + "\n"
        
        await callback.edit_message_text(
            text,
            reply_markup=keyboards.queue_navigation(chat_id, page, total_pages)
        )
    
    elif action == "nav":
        page = int(data[2])
        queue = queue_manager.get_queue(chat_id)
        tracks, total_pages = queue.get_page(page, 10)
        
        text = get_text(callback.from_user, "queue_title", page=page, total_pages=total_pages) + "\n\n"
        
        for i, track in enumerate(tracks, (page - 1) * 10 + 1):
            text += get_text(
                callback.from_user,
                "queue_item",
                index=i,
                title=track.title,
                duration=formatting.duration(track.duration)
            ) + "\n"
        
        await callback.edit_message_text(
            text,
            reply_markup=keyboards.queue_navigation(chat_id, page, total_pages)
        )
    
    elif action == "close":
        # Return to player view
        if player and chat_id in player.playing_messages:
            msg = player.playing_messages[chat_id]
            queue = queue_manager.get_queue(chat_id)
            track = queue.current_track
            
            if track:
                text = get_text(
                    callback.from_user,
                    "now_playing",
                    title=track.title,
                    duration=formatting.duration(track.duration),
                    requester=track.requester_name,
                    progress_bar=formatting.progress_bar(0, track.duration, 15),
                    elapsed="00:00",
                    total=formatting.duration(track.duration)
                )
                
                await callback.edit_message_text(
                    text,
                    reply_markup=keyboards.player_controls(
                        chat_id,
                        is_paused=player.is_paused.get(chat_id, False)
                    )
                )


@Client.on_callback_query(filters.regex(r"^lang_set:"))
async def language_callback(client: Client, callback: CallbackQuery):
    """Handle language selection."""
    lang = callback.data.split(":")[1]
    
    entity_id = callback.from_user.id
    if callback.message.chat.type != "private":
        entity_id = callback.message.chat.id
    
    if i18n.set_language(entity_id, lang):
        await callback.answer(get_text(entity_id, "language_changed"))
        await callback.message.delete()
    else:
        await callback.answer("Error setting language", show_alert=True)


@Client.on_callback_query(filters.regex(r"^(volume_|loop_|shuffle|settings_)"))
async def settings_callbacks(client: Client, callback: CallbackQuery):
    """Handle settings callbacks."""
    data = callback.data.split(":")
    action = data[0]
    chat_id = int(data[1]) if len(data) > 1 else callback.message.chat.id
    
    # Check if user is admin
    member = await callback.message.chat.get_member(callback.from_user.id)
    if not member.privileges:
        await callback.answer(
            get_text(callback.from_user, "admin_only"),
            show_alert=True
        )
        return
    
    if action == "settings_close":
        # Return to player controls
        await callback.edit_message_reply_markup(
            keyboards.player_controls(
                chat_id,
                is_paused=player.is_paused.get(chat_id, False) if player else False
            )
        )
    
    elif action.startswith("volume_"):
        # Volume control (not implemented in MVP)
        await callback.answer("Volume control coming soon!", show_alert=True)
    
    elif action == "loop_toggle":
        queue = queue_manager.get_queue(chat_id)
        queue.loop_track = not queue.loop_track
        status = "ON" if queue.loop_track else "OFF"
        await callback.answer(f"Loop: {status}")
    
    elif action == "shuffle":
        queue = queue_manager.get_queue(chat_id)
        queue.shuffle()
        await callback.answer("Queue shuffled!")
