import discord
import logging
import json
import uuid
from datetime import datetime
from database import EncryptedDatabase

logger = logging.getLogger('discord_bot')

class MessageMonitor:
    """
    Monitor and log all Discord messages in an encrypted database.
    This service captures all messages across all channels the bot has access to.
    """
    
    def __init__(self, client, db_path, encryption_key):
        """
        Initialize the message monitor service.
        
        Args:
            client (discord.Client): The Discord client object
            db_path (str): Path to the SQLite database file
            encryption_key (str): Key used for encrypting sensitive data
        """
        self.client = client
        self.db = EncryptedDatabase(db_path, encryption_key)
        logger.info("MessageMonitor initialized")
        
        # Register message event handler
        @client.event
        async def on_message(message):
            await self.process_message(message)
    
    async def process_message(self, message):
        """
        Process and store a Discord message.
        
        Args:
            message (discord.Message): The Discord message object
        """
        try:
            # Skip messages from the bot itself to avoid circular logging
            if message.author == self.client.user:
                return
                
            # Extract all relevant data from the message
            attachments_data = []
            for attachment in message.attachments:
                attachments_data.append({
                    'id': str(attachment.id),
                    'filename': attachment.filename,
                    'url': attachment.url,
                    'size': attachment.size,
                    'content_type': attachment.content_type if hasattr(attachment, 'content_type') else None
                })
                
            # Format mentions for metadata
            mentions = {
                'users': [str(user.id) for user in message.mentions],
                'roles': [str(role.id) for role in message.role_mentions],
                'channels': [str(channel.id) for channel in message.channel_mentions]
            }
            
            # Get additional message flags and properties
            message_flags = {}
            for flag_name in dir(message.flags):
                if not flag_name.startswith('_') and isinstance(getattr(message.flags, flag_name), bool):
                    message_flags[flag_name] = getattr(message.flags, flag_name)
            
            # Create the message data dictionary
            message_data = {
                'message_id': str(message.id),
                'channel_id': str(message.channel.id),
                'guild_id': str(message.guild.id) if message.guild else "DM",
                'author_id': str(message.author.id),
                'author_name': f"{message.author.name}#{message.author.discriminator}" if hasattr(message.author, 'discriminator') else message.author.name,
                'content': message.content,
                'timestamp': message.created_at.isoformat(),
                'attachments': json.dumps(attachments_data) if attachments_data else None,
                'message_type': str(message.type.name) if hasattr(message.type, 'name') else str(message.type),
                'is_bot': message.author.bot,
                'metadata': json.dumps({
                    'mentions': mentions,
                    'embeds_count': len(message.embeds),
                    'flags': message_flags,
                    'pinned': message.pinned,
                    'system_content': message.system_content if hasattr(message, 'system_content') else None,
                    'reference': str(message.reference.message_id) if message.reference else None
                })
            }
            
            # Store in database
            self.db.store_message(message_data)
            logger.debug(f"Stored message {message.id} from user {message.author.name}")
            
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
    
    def close(self):
        """Close the database connection"""
        self.db.close()