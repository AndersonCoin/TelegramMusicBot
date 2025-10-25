from pyrogram import Client, filters
from pyrogram.types import Message
from py_tgcalls import PyTgCalls
from config import Config
import asyncio

# Initialize bot and PyTgCalls
app = Client(
    "MusicBot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)

pytgcalls = PyTgCalls(app)

# Queue management
queues = {}

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message: Message):
    await message.reply_text(
        "🎵 **Music Bot Active!**\n\n"
        "I can play music in your group's voice chat.\n\n"
        "**Available Commands:**\n"
        "/play [song name/youtube link] - Play a song\n"
        "/pause - Pause playback\n"
        "/resume - Resume playback\n"
        "/skip - Skip current song\n"
        "/stop - Stop playback and clear queue\n"
        "/queue - Show current queue\n"
        "/volume [1-100] - Adjust volume\n\n"
        "Add me to your group and promote me as admin!"
    )

# Run the bot
async def main():
    await app.start()
    await pytgcalls.start()
    print("✅ Bot Started Successfully!")
    await pytgcalls.idle()
    await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
