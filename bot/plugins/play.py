import logging
from pyrogram import Client, filters
from pyrogram.types import Message

from bot.helpers.localization import get_text
from bot.helpers.decorators import group_only
from bot.helpers.youtube import download_audio
from bot.helpers.assistant import ensure_assistant
from bot.helpers.keyboards import get_player_keyboard
from bot.core.player import player
from bot.core.queue import queue_manager, Track

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("play") & filters.group)
@group_only
async def play_command(client: Client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if len(message.command) < 2:
        await message.reply(get_text(user_id, "usage_play"))
        return
    
    query = message.text.split(None, 1)[1]
    status_msg = await message.reply(get_text(user_id, "searching"))

    # Ensure assistant is ready
    if not await ensure_assistant(client, chat_id):
        await status_msg.edit(get_text(user_id, "assistant_error"))
        return

    try:
        await status_msg.edit(get_text(user_id, "downloading"))
        audio_info = await download_audio(query)

        track_meta = {'now_playing_message_id': status_msg.id}
        track = Track(
            title=audio_info['title'],
            duration=audio_info['duration'],
            requested_by=message.from_user.mention,
            file_path=audio_info['file_path'],
            url=audio_info['url'],
            thumbnail=audio_info.get('thumbnail'),
            meta=track_meta
        )

        queue = queue_manager.get_queue(chat_id)
        if queue.current_track is None:
            await status_msg.edit(get_text(user_id, "starting_playback"))
            if await player.play(chat_id, track):
                 # Progress updater will handle editing the message
                 pass
            else:
                await status_msg.edit(get_text(user_id, "play_error_no_vc"))
        else:
            position = queue.add(track)
            await status_msg.edit(
                get_text(
                    user_id,
                    "added_to_queue",
                    position=position,
                    title=track.title,
                    requester=track.requested_by
                ),
                reply_markup=get_player_keyboard(chat_id)
            )

    except Exception as e:
        logger.error(f"Play error: {e}", exc_info=True)
        await status_msg.edit(f"❌ Error: {e}")
