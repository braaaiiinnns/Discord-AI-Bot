import os
import json
import logging
import asyncio
import discord
from discord import Message, User, TextChannel, Member, Guild, Reaction, Embed, Activity, ActivityType
from typing import Dict, List, Any, Optional, Union, Callable, Awaitable
from datetime import datetime, timezone
import uuid
import random
import re
import traceback

from utils.database import UnifiedDatabase
from config.config import FILES_DIRECTORY

logger = logging.getLogger('discord_bot')

class MessageListener:
    def __init__(self, name: str, regex_pattern: str, callback: Callable[[Message, re.Match], Awaitable[None]], 
                 priority: int = 0, enabled: bool = True,
                 ignore_bot: bool = True, human_only: bool = False):
        """
        Initialize a message listener.
        
        Args:
            name (str): The name of the listener
            regex_pattern (str): The regex pattern to match against messages
            callback (callable): The function to call when a message matches
            priority (int): The priority of the listener (higher executes first)
            enabled (bool): Whether this listener is enabled
            ignore_bot (bool): Whether to ignore bot messages
            human_only (bool): Whether to only trigger on messages from humans
        """
        self.name = name
        self.pattern = regex_pattern
        self.regex = re.compile(regex_pattern, re.IGNORECASE)
        self.callback = callback
        self.priority = priority
        self.enabled = enabled
        self.ignore_bot = ignore_bot
        self.human_only = human_only

class MessageMonitor:
    def __init__(self, db: UnifiedDatabase, encryption_key: str):
        """
        Initialize the message monitor.
        
        Args:
            db (UnifiedDatabase): The unified database to store messages and AI interactions
            encryption_key (str): The key for encrypting sensitive data
        """
        logger.info("Initializing MessageMonitor with unified database")
        self.db = db
        self.encryption_key = encryption_key
        self.listeners: List[MessageListener] = []
        self.listeners_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'message_listeners.json')
        self.client = None  # Will be set by the bot when it initializes
        self._load_listeners()
        logger.info(f"Loaded {len(self.listeners)} message listeners")
    
    def set_client(self, client):
        """Set the Discord client reference."""
        self.client = client
        # Also set it in the database so it can access Discord data if needed
        self.db.set_discord_client(client)
        logger.info("Discord client reference set in MessageMonitor")

    def get_database(self):
        """Get the database instance."""
        return self.db

    def _load_listeners(self):
        """Load message listeners from file."""
        try:
            if os.path.exists(self.listeners_file):
                with open(self.listeners_file, 'r') as f:
                    listeners_data = json.load(f)
                
                # Clear existing listeners
                self.listeners = []
                
                # Create placeholder callback - will be replaced at runtime
                async def placeholder_callback(message, match):
                    logger.warning(f"Placeholder callback called for {message.content}")
                    pass
                
                # Add listeners from file
                for listener_data in listeners_data:
                    listener = MessageListener(
                        name=listener_data['name'],
                        regex_pattern=listener_data['pattern'],
                        callback=placeholder_callback,  # Will be replaced
                        priority=listener_data.get('priority', 0),
                        enabled=listener_data.get('enabled', True),
                        ignore_bot=listener_data.get('ignore_bot', True),
                        human_only=listener_data.get('human_only', False)
                    )
                    self.listeners.append(listener)
        except Exception as e:
            logger.error(f"Error loading message listeners: {e}", exc_info=True)
            # Create empty file if it doesn't exist
            if not os.path.exists(self.listeners_file):
                os.makedirs(os.path.dirname(self.listeners_file), exist_ok=True)
                with open(self.listeners_file, 'w') as f:
                    json.dump([], f)

    def save_listeners(self):
        """Save message listeners to file."""
        try:
            listeners_data = []
            for listener in self.listeners:
                listeners_data.append({
                    'name': listener.name,
                    'pattern': listener.pattern,
                    'priority': listener.priority,
                    'enabled': listener.enabled,
                    'ignore_bot': listener.ignore_bot,
                    'human_only': listener.human_only
                })
            
            os.makedirs(os.path.dirname(self.listeners_file), exist_ok=True)
            with open(self.listeners_file, 'w') as f:
                json.dump(listeners_data, f, indent=2)
            
            logger.info(f"Saved {len(listeners_data)} message listeners")
        except Exception as e:
            logger.error(f"Error saving message listeners: {e}", exc_info=True)

    def add_listener(self, name: str, regex_pattern: str,
                    callback: Callable[[Message, re.Match], Awaitable[None]],
                    priority: int = 0, enabled: bool = True,
                    ignore_bot: bool = True, human_only: bool = False) -> MessageListener:
        """
        Add a message listener.
        
        Args:
            name (str): The name of the listener
            regex_pattern (str): The regex pattern to match against messages
            callback (callable): The function to call when a message matches
            priority (int): The priority of the listener (higher executes first)
            enabled (bool): Whether this listener is enabled
            ignore_bot (bool): Whether to ignore bot messages
            human_only (bool): Whether to only trigger on messages from humans
            
        Returns:
            MessageListener: The created listener
        """
        listener = MessageListener(
            name=name,
            regex_pattern=regex_pattern,
            callback=callback,
            priority=priority,
            enabled=enabled,
            ignore_bot=ignore_bot,
            human_only=human_only
        )
        self.listeners.append(listener)
        
        # Sort listeners by priority (higher first)
        self.listeners.sort(key=lambda l: l.priority, reverse=True)
        
        self.save_listeners()
        return listener

    def remove_listener(self, name: str) -> bool:
        """
        Remove a message listener.
        
        Args:
            name (str): The name of the listener
            
        Returns:
            bool: Whether the listener was removed
        """
        initial_count = len(self.listeners)
        self.listeners = [l for l in self.listeners if l.name != name]
        removed = len(self.listeners) < initial_count
        if removed:
            self.save_listeners()
        return removed

    def get_listener(self, name: str) -> Optional[MessageListener]:
        """
        Get a message listener.
        
        Args:
            name (str): The name of the listener
            
        Returns:
            Optional[MessageListener]: The listener if found, None otherwise
        """
        for listener in self.listeners:
            if listener.name == name:
                return listener
        return None

    def enable_listener(self, name: str) -> bool:
        """
        Enable a message listener.
        
        Args:
            name (str): The name of the listener
            
        Returns:
            bool: Whether the listener was enabled
        """
        listener = self.get_listener(name)
        if listener:
            listener.enabled = True
            self.save_listeners()
            return True
        return False

    def disable_listener(self, name: str) -> bool:
        """
        Disable a message listener.
        
        Args:
            name (str): The name of the listener
            
        Returns:
            bool: Whether the listener was disabled
        """
        listener = self.get_listener(name)
        if listener:
            listener.enabled = False
            self.save_listeners()
            return True
        return False

    def update_listener_callback(self, name: str, callback: Callable[[Message, re.Match], Awaitable[None]]) -> bool:
        """
        Update a listener's callback function.
        
        Args:
            name (str): The name of the listener
            callback (callable): The new callback function
            
        Returns:
            bool: Whether the callback was updated
        """
        listener = self.get_listener(name)
        if listener:
            listener.callback = callback
            return True
        return False

    async def process_message(self, message: Message) -> bool:
        """
        Process a message and store it in the database.
        
        Args:
            message (Message): The Discord message to process
            
        Returns:
            bool: Whether the message was stored successfully
        """
        try:
            # Don't process system messages
            if message.type != discord.MessageType.default:
                return False
                
            # Extract message data
            guild_name = message.guild.name if message.guild else "DM"
            author_name = f"{message.author.name}"
            channel_name = f"{message.channel.name}" if hasattr(message.channel, "name") else "Unknown"
            
            logger.debug(f"Processing message from {author_name} in {guild_name}/{channel_name}: {message.content[:30]}...")
            
            # Store message in unified database
            timestamp = message.created_at.isoformat()
            message_data = {
                'message_id': str(message.id),
                'channel_id': str(message.channel.id),
                'guild_id': str(message.guild.id) if message.guild else "0",
                'author_id': str(message.author.id),
                'author_name': author_name,
                'content': message.content,
                'timestamp': timestamp,
                'message_type': str(message.type.name),
                'is_bot': message.author.bot,
                'attachments': []
            }
            
            # Process attachments
            if message.attachments:
                message_data['attachments'] = [
                    {
                        'id': str(attachment.id),
                        'filename': attachment.filename,
                        'url': attachment.url,
                        'proxy_url': attachment.proxy_url,
                        'size': attachment.size,
                        'height': attachment.height,
                        'width': attachment.width,
                        'content_type': attachment.content_type if hasattr(attachment, 'content_type') else None
                    }
                    for attachment in message.attachments
                ]
            
            # Store message in unified database
            success = await self.db.store_message(message_data)
            
            if success and message.attachments:
                # Download and store files
                files = await self.db.store_message_files(message_data)
                if files:
                    logger.debug(f"Stored {len(files)} files for message {message.id}")
            
            # Store channel information if available
            if message.channel and isinstance(message.channel, TextChannel) and message.guild:
                await self.store_channel(message.channel)
            
            # Process message listeners
            await self.process_listeners(message)
            
            return success
        except Exception as e:
            logger.error(f"Error processing message {message.id}: {e}", exc_info=True)
            return False

    async def process_listeners(self, message: Message) -> List[str]:
        """
        Process all message listeners on a message.
        
        Args:
            message (Message): The Discord message to process
            
        Returns:
            List[str]: The names of triggered listeners
        """
        triggered = []
        
        for listener in self.listeners:
            if not listener.enabled:
                continue
                
            # Check if we should ignore this message
            if listener.human_only and message.author.bot:
                continue
                
            if listener.ignore_bot and message.author.bot:
                continue
                
            # Check for regex pattern match
            match = listener.regex.search(message.content)
            if match:
                try:
                    logger.debug(f"Listener '{listener.name}' matched message {message.id}")
                    await listener.callback(message, match)
                    triggered.append(listener.name)
                except Exception as e:
                    logger.error(f"Error in listener '{listener.name}': {e}", exc_info=True)
        
        return triggered

    async def process_edit(self, before: Message, after: Message) -> bool:
        """
        Process a message edit and store changes.
        
        Args:
            before (Message): The message before the edit
            after (Message): The message after the edit
            
        Returns:
            bool: Whether the edit was stored successfully
        """
        try:
            # Skip if content didn't change
            if before.content == after.content:
                return False
                
            logger.debug(f"Processing edit for message {after.id}")
            
            # Prepare edit data
            edit_data = {
                'message_id': str(after.id),
                'channel_id': str(after.channel.id),
                'guild_id': str(after.guild.id) if after.guild else "0",
                'author_id': str(after.author.id),
                'original_content': before.content,
                'new_content': after.content,
                'edit_timestamp': after.edited_at.isoformat() if after.edited_at else datetime.now(timezone.utc).isoformat()
            }
            
            # Store edit in unified database
            success = await self.db.store_message_edit(edit_data)
            return success
        except Exception as e:
            logger.error(f"Error processing edit for message {after.id}: {e}", exc_info=True)
            return False

    async def store_channel(self, channel: TextChannel) -> bool:
        """
        Store channel information in database.
        
        Args:
            channel (TextChannel): The Discord channel to store
            
        Returns:
            bool: Whether the channel was stored successfully
        """
        try:
            if not hasattr(channel, 'guild'):
                logger.debug(f"Skipping channel {channel.id} - no guild attribute")
                return False
                
            logger.debug(f"Storing channel {channel.name} ({channel.id})")
            
            # Prepare channel data
            channel_data = {
                'channel_id': str(channel.id),
                'guild_id': str(channel.guild.id) if channel.guild else "0",
                'channel_name': channel.name if hasattr(channel, 'name') else "Unknown",
                'channel_type': str(channel.type.name),
                'last_update': datetime.now().isoformat()
            }
            
            # Store channel in unified database
            success = await self.db.store_channel(channel_data)
            return success
        except Exception as e:
            logger.error(f"Error storing channel {channel.id}: {e}", exc_info=True)
            return False

    async def store_channels(self, guild: Guild) -> int:
        """
        Store all channels in a guild.
        
        Args:
            guild (Guild): The Discord guild to scan
            
        Returns:
            int: Number of channels stored
        """
        stored = 0
        
        for channel in guild.channels:
            if isinstance(channel, TextChannel):
                if await self.store_channel(channel):
                    stored += 1
        
        logger.debug(f"Stored {stored} channels from guild {guild.name} ({guild.id})")
        return stored

    async def process_reaction(self, reaction: Reaction, user: Union[User, Member]) -> bool:
        """
        Process a reaction and store it.
        
        Args:
            reaction (Reaction): The Discord reaction to process
            user (Union[User, Member]): The user who added the reaction
            
        Returns:
            bool: Whether the reaction was stored successfully
        """
        try:
            message = reaction.message
            emoji = reaction.emoji
            
            # Skip reactions to system messages
            if message.type != discord.MessageType.default:
                return False
                
            logger.debug(f"Processing reaction {emoji} from user {user.name} on message {message.id}")
            
            # Create a unique ID for the reaction
            reaction_id = str(uuid.uuid4())
            
            # Prepare reaction data
            reaction_data = {
                'reaction_id': reaction_id,
                'message_id': str(message.id),
                'user_id': str(user.id),
                'emoji_name': emoji.name if hasattr(emoji, 'name') else str(emoji),
                'emoji_id': str(emoji.id) if hasattr(emoji, 'id') else None,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            # Store in unified database
            conn = self.db._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
            INSERT INTO reactions (
                reaction_id, message_id, user_id, emoji_name, emoji_id, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                reaction_data['reaction_id'],
                reaction_data['message_id'],
                reaction_data['user_id'],
                reaction_data['emoji_name'],
                reaction_data['emoji_id'],
                reaction_data['timestamp']
            ))
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error processing reaction: {e}", exc_info=True)
            return False

    async def store_ai_interaction(self, interaction_data: Dict[str, Any]) -> bool:
        """
        Store an AI interaction in the unified database.
        
        Args:
            interaction_data (dict): AI interaction data
            
        Returns:
            bool: Whether the interaction was stored successfully
        """
        try:
            # Generate a UUID if not provided
            if 'interaction_id' not in interaction_data:
                interaction_data['interaction_id'] = str(uuid.uuid4())
                
            # Add timestamp if not provided
            if 'timestamp' not in interaction_data:
                interaction_data['timestamp'] = datetime.now(timezone.utc).isoformat()
                
            logger.debug(f"Storing AI interaction {interaction_data['interaction_id']}")
            
            # Store in unified database
            success = await self.db.store_ai_interaction(interaction_data)
            
            if not success:
                logger.error(f"Failed to store AI interaction {interaction_data['interaction_id']}")
                
            return success
        except Exception as e:
            logger.error(f"Error storing AI interaction: {e}", exc_info=True)
            return False
            
    async def backup_database(self, backup_path: str = None) -> bool:
        """
        Create a backup of the database.
        
        Args:
            backup_path (str, optional): Path to store the backup. If None, 
                                        a timestamped backup will be created.
            
        Returns:
            bool: Success status
        """
        try:
            # Get the current database path
            db_path = self.db.db_path
            
            # Generate backup path if not provided
            if not backup_path:
                timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
                backup_path = f"{db_path}.bak-{timestamp}"
            else:
                backup_path = f"{backup_path}"
                
            logger.info(f"Creating database backup at {backup_path}")
            
            # Connect to the database (need raw connection to use with backup)
            conn = sqlite3.connect(db_path)
            
            # Make backup
            backup_conn = sqlite3.connect(backup_path)
            conn.backup(backup_conn)
            
            # Close connections
            backup_conn.close()
            conn.close()
            
            logger.info(f"Database backup created successfully at {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Error backing up database: {e}", exc_info=True)
            return False
            
    async def migrate_database(self, messages_db_path: str, ai_interactions_db_path: str, source_encryption_key: str = None) -> Dict[str, Any]:
        """
        Migrate data from old separate database files to the unified database.
        
        Args:
            messages_db_path (str): Path to old messages database
            ai_interactions_db_path (str): Path to old AI interactions database
            source_encryption_key (str, optional): Encryption key used in source databases, if different
            
        Returns:
            Dict[str, Any]: Migration statistics
        """
        try:
            logger.info("Starting database migration...")
            
            # Check if the old database files exist
            messages_exists = os.path.exists(messages_db_path)
            ai_exists = os.path.exists(ai_interactions_db_path)
            
            if not messages_exists and not ai_exists:
                logger.warning("No existing databases found for migration")
                return {"error": "No existing databases found for migration"}
                
            # Start migration
            stats = await self.db.migrate_from_old_databases(messages_db_path, ai_interactions_db_path, source_encryption_key)
            
            logger.info(f"Migration completed: {stats['messages_migrated']} messages, {stats['ai_interactions_migrated']} AI interactions migrated")
            
            if len(stats['errors']) > 0:
                logger.warning(f"Migration completed with {len(stats['errors'])} errors")
                
            return stats
        except Exception as e:
            logger.error(f"Error during database migration: {e}", exc_info=True)
            return {"error": str(e)}

    async def get_stats(self, days: int = 30, guild_id: str = None) -> Dict[str, Any]:
        """
        Get database statistics.
        
        Args:
            days (int): Number of days to include in stats
            guild_id (str, optional): Guild ID to filter by
            
        Returns:
            Dict[str, Any]: Statistics data
        """
        try:
            return await self.db.get_stats(days, guild_id)
        except Exception as e:
            logger.error(f"Error getting stats: {e}", exc_info=True)
            return {"error": str(e)}
            
    def close(self):
        """Close the database connection and any other resources."""
        logger.debug("Closing MessageMonitor resources...")
        try:
            if hasattr(self, 'db') and self.db:
                logger.debug("Closing database connection.")
                self.db.close()
                logger.debug("Database connection closed.")
        except Exception as e:
            logger.error(f"Error closing database connection: {e}", exc_info=True)

    async def process_message_edit(self, before, after):
        """
        Process a message edit event.
        
        Args:
            before (Message): The message before the edit
            after (Message): The message after the edit
            
        Returns:
            bool: Whether the edit was processed successfully
        """
        try:
            logger.debug(f"Process message edit called for: {after.id}")
            # Use the existing process_edit method to handle the actual processing
            result = await self.process_edit(before, after)
            return result
        except Exception as e:
            logger.error(f"Error in process_message_edit: {e}", exc_info=True)
            return False