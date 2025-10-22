from pyrogram import Client, filters
from pyrogram.types import Message
from bot.helpers.decorators import group_only, admin_only
from bot.helpers.localization import get_text
from bot.core.player import player

@Client.on_message(filters.command("pause") & filters.group)
@group_only
@admin_only
async def pause_command(client: Client, message: Message):
    await player.pause(message.chat.id)
    await message.reply(get_text(message.from_user.id, "paused"))

@Client.on_message(filters.command("resume") & filters.group)
@group_only
@admin_only
async def resume_command(client: Client, message: Message):
    await player.resume(message.chat.id)
    await message.reply(get_text(message.from_user.id, "resumed"))

@Client.on_message(filters.command("skip") & filters.group)
@group_only
@admin_only
async def skip_command(client: Client, message: Message):
    next_track = await player.skip(message.chat.id)
    if next_track:
        await message.reply(get_text(message.from_user.id, "skipped"))
    else:
        await message.reply(get_text(message.from_user.id, "queue_empty"))

@Client.on_message(filters.command("stop") & filters.group)
@group_only
@admin_only
async def stop_command(client: Client, message: Message):
    await player.stop(message.chat.id)
    await message.reply(get_text(message.from_user.id, "stopped"))
