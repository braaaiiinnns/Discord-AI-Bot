import os
import json
import logging
import asyncio
import discord
from discord import Message, User, TextChannel, Member, Guild, Reaction, Embed, Activity, ActivityType
from typing import Dict, List, Any, Optional, Union, Callable, Awaitable
from datetime import datetime, timezone, timedelta
import uuid
import random
import re
import traceback
import time
from collections import OrderedDict
import sqlite3

from utils.database import UnifiedDatabase
from config.storage_config import FILES_DIRECTORY

logger = logging.getLogger('discord_bot')

class LRUCache(OrderedDict):
    """LRU Cache implementation based on OrderedDict"""
    def __init__(self, capacity: int):
        self.capacity = capacity
        super().__init__()

    def get(self, key):
        if key not in self:
            return None
        self.move_to_end(key)
        return self[key]

    def put(self, key, value):
        if key in self:
            self.move_to_end(key)
        self[key] = value
        if len(self) > self.capacity:
            self.popitem(last=False)

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
    def __init__(self, db: UnifiedDatabase, encryption_key: str, 
                 max_cached_messages: int = 500,
                 max_cached_channels: int = 100):
        """
        Initialize the message monitor.
        
        Args:
            db (UnifiedDatabase): The unified database to store messages and AI interactions
            encryption_key (str): The key for encrypting sensitive data
            max_cached_messages (int): Maximum number of messages to cache
            max_cached_channels (int): Maximum number of channels to cache
        """
        logger.info(f"Initializing MessageMonitor with unified database (cache size: {max_cached_messages})")
        self.db = db
        self.encryption_key = encryption_key
        self.listeners: List[MessageListener] = []
        self.listeners_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'message_listeners.json')
        self.client = None  # Will be set by the bot when it initializes
        
        # Initialize caches
        self.message_cache = LRUCache(max_cached_messages)
        self.channel_cache = LRUCache(max_cached_channels) 
        self.guild_cache = LRUCache(50)
        self.user_cache = LRUCache(200)
        
        # Performance tracking
        self.processing_times = []
        self.max_processing_samples = 100
        
        self._load_listeners()
        logger.info(f"Loaded {len(self.listeners)} message listeners")
    
    def set_client(self, client):
        """Set the Discord client reference."""
        self.client = client
        # Also set it in the database so it can access Discord data if needed
        self.db.set_discord_client(client)
        logger.info("Discord client reference set in MessageMonitor")

    def get_database(self):
        """
        Get the database instance.
        
        Returns:
            The database instance or None if not available
        """
        try:
            if hasattr(self, 'db') and self.db is not None:
                logger.debug("Successfully retrieved database from MessageMonitor")
                return self.db
            else:
                logger.warning("Database not initialized in MessageMonitor")
                return None
        except Exception as e:
            logger.error(f"Error retrieving database from MessageMonitor: {e}", exc_info=True)
            return None

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
                    # Use 'trigger_value' instead of 'pattern'
                    regex_pattern = listener_data.get('trigger_value') 
                    if not regex_pattern:
                        logger.warning(f"Listener '{listener_data.get('name', 'Unnamed')}' is missing 'trigger_value'. Skipping.")
                        continue
                        
                    # Handle case where trigger_value might be a list (for contains_any)
                    # For simplicity in MessageListener, we'll join list triggers with | for regex
                    # A more robust solution might involve handling trigger_type directly in process_listeners
                    if isinstance(regex_pattern, list):
                        # Escape special regex characters in each item before joining
                        regex_pattern = '|'.join(re.escape(item) for item in regex_pattern)
                    
                    listener = MessageListener(
                        name=listener_data['name'],
                        # Pass the extracted/processed regex_pattern
                        regex_pattern=regex_pattern, 
                        callback=placeholder_callback,  # Will be replaced
                        priority=listener_data.get('priority', 0),
                        enabled=listener_data.get('enabled', True),
                        # Read ignore_case from JSON, default to True if not present
                        ignore_bot=listener_data.get('ignore_bot', True), 
                        human_only=listener_data.get('human_only', False)
                        # Note: ignore_case is handled by re.IGNORECASE flag during compile
                    )
                    # Compile regex with ignore_case flag from JSON if available
                    ignore_case_flag = re.IGNORECASE if listener_data.get('ignore_case', True) else 0
                    listener.regex = re.compile(listener.pattern, ignore_case_flag)
                    
                    self.listeners.append(listener)
            # Sort listeners by priority (higher first) - Moved outside the loop
            self.listeners.sort(key=lambda l: l.priority, reverse=True)

        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from {self.listeners_file}: {e}", exc_info=True)
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
                # Save using the 'trigger_value' key to match the loading logic
                listeners_data.append({
                    'name': listener.name,
                    # Save the original pattern string used to create the listener
                    'trigger_value': listener.pattern, 
                    'priority': listener.priority,
                    'enabled': listener.enabled,
                    'ignore_bot': listener.ignore_bot,
                    'human_only': listener.human_only,
                    # Persist ignore_case setting (derived from regex flags)
                    'ignore_case': bool(listener.regex.flags & re.IGNORECASE)
                    # Add back other fields if needed for other cogs (description, action_type etc.)
                    # 'description': listener_data.get('description', ''), # Example
                    # 'action_type': listener_data.get('action_type', ''), # Example
                    # 'action_value': listener_data.get('action_value', '') # Example
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
        Process a message and store it in the database with performance tracking.
        
        Args:
            message (Message): The Discord message to process
            
        Returns:
            bool: Whether the message was stored successfully
        """
        start_time = time.time()
        
        try:
            # Check if we've already processed this message recently
            message_id = str(message.id)
            if self.message_cache.get(message_id):
                logger.debug(f"Skipping already processed message {message_id}")
                return True
                
            # Don't process system messages
            if message.type != discord.MessageType.default:
                return False
                
            # Extract message data
            guild = message.guild
            author = message.author
            channel = message.channel
            
            # Use cache for guild data if possible
            guild_id = str(guild.id) if guild else "0"
            if guild and guild_id not in self.guild_cache:
                self.guild_cache.put(guild_id, {
                    'name': guild.name,
                    'member_count': guild.member_count if hasattr(guild, 'member_count') else 0
                })
            guild_name = self.guild_cache.get(guild_id)['name'] if guild and self.guild_cache.get(guild_id) else "DM"
            
            # Use cache for author data
            author_id = str(author.id)
            if author_id not in self.user_cache:
                self.user_cache.put(author_id, {
                    'name': author.name,
                    'discriminator': author.discriminator if hasattr(author, 'discriminator') else None,
                    'bot': author.bot
                })
            author_data = self.user_cache.get(author_id)
            author_name = author_data['name'] if author_data else author.name
            
            # Use cache for channel data
            channel_id = str(channel.id) if channel else "0"
            if channel and channel_id not in self.channel_cache:
                channel_name = channel.name if hasattr(channel, "name") else "Unknown"
                self.channel_cache.put(channel_id, {
                    'name': channel_name,
                    'type': str(channel.type) if hasattr(channel, 'type') else "Unknown"
                })
            channel_data = self.channel_cache.get(channel_id)
            channel_name = channel_data['name'] if channel_data else "Unknown"
            
            logger.debug(f"Processing message from {author_name} in {guild_name}/{channel_name}: {message.content[:30]}...")
            
            # Store message in unified database
            timestamp = message.created_at.isoformat()
            message_data = {
                'message_id': message_id,
                'channel_id': channel_id,
                'guild_id': guild_id,
                'author_id': author_id,
                'author_name': author_name,
                'content': message.content,
                'timestamp': timestamp,
                'message_type': str(message.type.name),
                'is_bot': author.bot,
                'attachments': []
            }
            
            # Process attachments - only extract minimal data first
            if message.attachments:
                message_data['attachments'] = [
                    {
                        'id': str(attachment.id),
                        'filename': attachment.filename,
                        'url': attachment.url,
                        'size': attachment.size
                    }
                    for attachment in message.attachments
                ]
            
            # Store message in unified database with batch processing if available
            db_start_time = time.time()
            success = await self.db.store_message(message_data)
            db_time = time.time() - db_start_time
            
            if success:
                # Add to cache to avoid duplicate processing
                self.message_cache.put(message_id, {
                    'timestamp': timestamp,
                    'author_id': author_id,
                    'content': message.content[:100]  # Store only first 100 chars
                })
                
                # Process attachments in background if there are any
                if message.attachments:
                    # Create a background task to download and store files
                    asyncio.create_task(self._store_attachments(message_data, message.attachments))
            
            # Store channel information if available - only if not in cache
            if channel and isinstance(channel, TextChannel) and guild and channel_id not in self.channel_cache:
                await self.store_channel(channel)
            
            # Process message listeners in background to avoid slowing down message processing
            asyncio.create_task(self.process_listeners(message))
            
            # Track processing time
            process_time = time.time() - start_time
            self.processing_times.append(process_time)
            if len(self.processing_times) > self.max_processing_samples:
                self.processing_times.pop(0)
            
            # Log performance metrics periodically
            if message_id.endswith('000'):  # Log every 1000 messages
                avg_time = sum(self.processing_times) / len(self.processing_times)
                logger.info(f"Message processing performance: avg={avg_time:.4f}s, db={db_time:.4f}s, cache_size={len(self.message_cache)}")
            
            return success
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(f"Error processing message {message.id} (took {process_time:.4f}s): {e}", exc_info=True)
            return False
    
    async def _store_attachments(self, message_data: Dict[str, Any], attachments: List[Any]) -> bool:
        """
        Store message attachments in the database and filesystem.
        
        Args:
            message_data (dict): The message data
            attachments (list): The Discord message attachments
            
        Returns:
            bool: Whether the attachments were stored successfully
        """
        try:
            # Enhance attachment data with full details
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
                for attachment in attachments
            ]
            
            # Store files in database and filesystem
            files = await self.db.store_message_files(message_data)
            if files:
                logger.debug(f"Stored {len(files)} files for message {message_data['message_id']}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error storing attachments for message {message_data['message_id']}: {e}", exc_info=True)
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
            
    async def close(self):
        """Close the database connection and any other resources."""
        logger.debug("Closing MessageMonitor resources...")
        try:
            if hasattr(self, 'db') and self.db:
                logger.debug("Closing database connection.")
                # Await the async close method
                await self.db.close()
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