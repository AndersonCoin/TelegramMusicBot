"""Assistant management utilities."""

import logging
from pyrogram.types import ChatPrivileges
from pyrogram.errors import (
    ChatAdminRequired,
    UserNotParticipant,
    UserPrivacyRestricted,
    PeerIdInvalid
)

logger = logging.getLogger(__name__)

class AssistantManager:
    """Manages assistant user operations."""
    
    @staticmethod
    async def ensure_in_chat(client, chat_id: int) -> tuple[bool, str]:
        """Ensure assistant is in chat and has permissions."""
        try:
            # Check if assistant is in chat
            try:
                member = await client.bot.get_chat_member(
                    chat_id, 
                    client.assistant_id
                )
                
                # Check if has video chat permission
                if member.privileges and member.privileges.can_manage_video_chats:
                    return True, "ready"
                    
                # Need to promote
                return await AssistantManager.promote_assistant(client, chat_id)
                
            except UserNotParticipant:
                # Invite assistant
                success, msg = await AssistantManager.invite_assistant(client, chat_id)
                if not success:
                    return False, msg
                    
                # Promote after invitation
                return await AssistantManager.promote_assistant(client, chat_id)
                
        except Exception as e:
            logger.error(f"Assistant check failed: {e}")
            return False, str(e)
    
    @staticmethod
    async def invite_assistant(client, chat_id: int) -> tuple[bool, str]:
        """Invite assistant to chat."""
        try:
            # Get chat invite link
            chat = await client.bot.get_chat(chat_id)
            
            if chat.username:
                # Public chat
                await client.assistant.join_chat(chat.username)
            else:
                # Private chat - create invite link
                link = await client.bot.export_chat_invite_link(chat_id)
                await client.assistant.join_chat(link)
                await client.bot.revoke_chat_invite_link(chat_id, link)
            
            return True, "assistant_invited"
            
        except UserPrivacyRestricted:
            return False, "Assistant privacy settings prevent joining"
        except ChatAdminRequired:
            return False, "Bot needs admin rights to invite assistant"
        except Exception as e:
            logger.error(f"Failed to invite assistant: {e}")
            return False, str(e)
    
    @staticmethod
    async def promote_assistant(client, chat_id: int) -> tuple[bool, str]:
        """Promote assistant with video chat permissions."""
        try:
            await client.bot.promote_chat_member(
                chat_id,
                client.assistant_id,
                privileges=ChatPrivileges(
                    can_manage_video_chats=True
                )
            )
            return True, "assistant_promoted"
            
        except ChatAdminRequired:
            return False, "Bot needs admin rights to promote assistant"
        except Exception as e:
            logger.error(f"Failed to promote assistant: {e}")
            return False, str(e)
