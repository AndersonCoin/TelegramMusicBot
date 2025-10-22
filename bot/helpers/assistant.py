import logging
from pyrogram import Client
from pyrogram.errors import UserAlreadyParticipant, UserNotParticipant, UserPrivacyRestricted
from pyrogram.types import ChatPrivileges
from config import Config

logger = logging.getLogger(__name__)

async def ensure_assistant(client: Client, chat_id: int) -> bool:
    assistant_username = Config.ASSISTANT_USERNAME
    try:
        await client.get_chat_member(chat_id, assistant_username)
    except UserNotParticipant:
        try:
            logger.info(f"Inviting assistant @{assistant_username} to chat {chat_id}")
            await client.add_chat_members(chat_id, assistant_username)
        except UserPrivacyRestricted:
            logger.error(f"Cannot invite @{assistant_username} due to privacy settings.")
            return False
        except Exception as e:
            logger.error(f"Failed to invite @{assistant_username}: {e}")
            return False

    try:
        member = await client.get_chat_member(chat_id, assistant_username)
        if not member.privileges or not member.privileges.can_manage_video_chats:
            logger.info(f"Promoting @{assistant_username} in {chat_id}")
            await client.promote_chat_member(
                chat_id,
                assistant_username,
                privileges=ChatPrivileges(can_manage_video_chats=True)
            )
    except Exception as e:
        logger.error(f"Failed to promote @{assistant_username}: {e}")
        return False
        
    return True
