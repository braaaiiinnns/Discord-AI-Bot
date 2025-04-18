import sqlite3
import os
import json
import logging
import requests
import hashlib
import aiohttp
import asyncio
from datetime import datetime
from utils.ncrypt import encrypt_data, decrypt_data
from typing import List, Dict, Any, Optional, Union, Callable
from queue import Queue, Empty  # Import Empty exception directly
from threading import Thread, Lock

logger = logging.getLogger('discord_bot')

class DatabaseQueue:
    """Thread-safe queue for database operations to prevent concurrent access issues with SQLite."""
    
    def __init__(self, max_workers=1):
        """
        Initialize the database queue.
        
        Args:
            max_workers (int): Maximum number of worker threads (usually 1 for SQLite)
        """
        self.queue = Queue()
        self.lock = Lock()
        self.workers = []
        self.running = True
        
        # Start worker threads
        for _ in range(max_workers):
            worker = Thread(target=self._worker_loop, daemon=True)
            worker.start()
            self.workers.append(worker)
        
        logger.info(f"Database queue initialized with {max_workers} worker(s)")
    
    def _worker_loop(self):
        """Worker thread that processes database operations from the queue."""
        while self.running:
            try:
                # Get the next operation from the queue with a timeout
                # This allows the thread to check self.running periodically
                try:
                    operation, future = self.queue.get(timeout=1.0)
                except Empty:  # Fixed: Use the imported Empty exception directly
                    continue
                
                # Execute the operation
                try:
                    result = operation()
                    if not future.done():
                        future.set_result(result)
                except Exception as e:
                    if not future.done():
                        future.set_exception(e)
                finally:
                    self.queue.task_done()
            except Exception as e:
                logger.error(f"Error in database worker: {e}", exc_info=True)
    
    async def execute(self, operation: Callable) -> Any:
        """
        Add an operation to the queue and wait for its result.
        
        Args:
            operation: Callable that performs a database operation
            
        Returns:
            The result of the operation
        """
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        
        self.queue.put((operation, future))
        
        # Wait for the operation to complete
        return await future
    
    def stop(self):
        """Stop all worker threads."""
        self.running = False
        
        # Wait for all workers to finish
        for worker in self.workers:
            if worker.is_alive():
                worker.join(timeout=5.0)
        
        logger.info("Database queue stopped")

class EncryptedDatabase:
    """Database handler with encryption support for storing Discord messages, AI interactions, files, and reactions."""
    
    def __init__(self, db_path, encryption_key, create_tables=True):
        """
        Initialize the database connection.
        
        Args:
            db_path (str): Path to the SQLite database file
            encryption_key (str): Key used for encrypting sensitive data
            create_tables (bool): Whether to create tables if they don't exist
        """
        self.db_path = db_path
        self.encryption_key = encryption_key
        self.conn = None
        self.files_dir = os.path.join(os.path.dirname(db_path), "files")
        
        # Ensure the database and files directories exist
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        os.makedirs(self.files_dir, exist_ok=True)
        
        # Initialize connection
        self._connect()
        
        # Create database queue for thread-safe operations
        self.queue = DatabaseQueue(max_workers=1)
        
        # Create tables if requested
        if create_tables:
            self._create_tables()
    
    def _connect(self):
        """Establish a connection to the database."""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # Return rows as dictionary-like objects
            logger.info(f"Connected to database at {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def _create_tables(self):
        """Create necessary tables if they don't exist."""
        try:
            cursor = self.conn.cursor()
            
            # Messages table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                author_id TEXT NOT NULL,
                author_name TEXT NOT NULL,
                content_encrypted TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                attachments_encrypted TEXT,
                message_type TEXT NOT NULL,
                is_bot INTEGER NOT NULL,
                metadata_encrypted TEXT
            )
            ''')
            
            # AI interactions table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_interactions (
                interaction_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_encrypted TEXT NOT NULL,
                response_encrypted TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                tokens_used INTEGER,
                execution_time REAL,
                metadata_encrypted TEXT
            )
            ''')
            
            # Files table for storing downloaded files/images
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                file_id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                author_id TEXT NOT NULL,
                original_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                file_hash TEXT NOT NULL,
                original_url TEXT,
                timestamp TEXT NOT NULL,
                metadata_encrypted TEXT,
                FOREIGN KEY (message_id) REFERENCES messages (message_id)
            )
            ''')
            
            # Reactions table for storing message reactions
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS reactions (
                reaction_id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                emoji_name TEXT NOT NULL,
                emoji_id TEXT,
                timestamp TEXT NOT NULL,
                metadata_encrypted TEXT,
                FOREIGN KEY (message_id) REFERENCES messages (message_id)
            )
            ''')
            
            # Create indexes for faster querying (log(n) complexity with B-tree indexes)
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_author ON messages (author_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_guild ON messages (guild_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages (channel_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages (timestamp)')
            
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_user ON ai_interactions (user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_guild ON ai_interactions (guild_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_model ON ai_interactions (model)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_timestamp ON ai_interactions (timestamp)')
            
            # Indexes for files and reactions
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_message ON files (message_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_author ON files (author_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_type ON files (file_type)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_hash ON files (file_hash)')
            
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_reactions_message ON reactions (message_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_reactions_user ON reactions (user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_reactions_emoji ON reactions (emoji_name)')
            
            self.conn.commit()
            logger.info("Database tables created successfully")
        except sqlite3.Error as e:
            logger.error(f"Error creating tables: {e}")
            raise
    
    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
        self.queue.stop()
    
    def store_message(self, message_data):
        """
        Store a Discord message in the database.
        
        Args:
            message_data (dict): Message data to store
        
        Returns:
            bool: Success status
        """
        try:
            # Encrypt sensitive data
            if 'content' in message_data:
                message_data['content_encrypted'] = encrypt_data(message_data['content'], self.encryption_key)
                del message_data['content']
            else:
                message_data['content_encrypted'] = encrypt_data("", self.encryption_key)
                
            if 'attachments' in message_data and message_data['attachments']:
                message_data['attachments_encrypted'] = encrypt_data(message_data['attachments'], self.encryption_key)
                del message_data['attachments']
            else:
                message_data['attachments_encrypted'] = None
                
            if 'metadata' in message_data and message_data['metadata']:
                message_data['metadata_encrypted'] = encrypt_data(message_data['metadata'], self.encryption_key)
                del message_data['metadata']
            else:
                message_data['metadata_encrypted'] = None
            
            # Insert message into database
            cursor = self.conn.cursor()
            cursor.execute('''
            INSERT OR REPLACE INTO messages (
                message_id, channel_id, guild_id, author_id, author_name,
                content_encrypted, timestamp, attachments_encrypted,
                message_type, is_bot, metadata_encrypted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                message_data['message_id'],
                message_data['channel_id'],
                message_data['guild_id'],
                message_data['author_id'],
                message_data['author_name'],
                message_data['content_encrypted'],
                message_data['timestamp'],
                message_data['attachments_encrypted'],
                message_data['message_type'],
                1 if message_data['is_bot'] else 0,
                message_data['metadata_encrypted']
            ))
            
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error storing message: {e}", exc_info=True)
            if self.conn:
                self.conn.rollback()
            return False
    
    def store_message_edit(self, edit_data):
        """
        Store a Discord message edit in the database.
        
        Args:
            edit_data (dict): Edit data to store including before and after content
        
        Returns:
            bool: Success status
        """
        try:
            # Create message_edits table if it doesn't exist
            cursor = self.conn.cursor()
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS message_edits (
                edit_id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                author_id TEXT NOT NULL,
                before_content_encrypted TEXT NOT NULL,
                after_content_encrypted TEXT NOT NULL,
                edit_timestamp TEXT NOT NULL,
                attachments_encrypted TEXT,
                metadata_encrypted TEXT,
                FOREIGN KEY (message_id) REFERENCES messages (message_id)
            )
            ''')
            
            # Encrypt sensitive data
            if 'before_content' in edit_data:
                edit_data['before_content_encrypted'] = encrypt_data(edit_data['before_content'], self.encryption_key)
                del edit_data['before_content']
            else:
                edit_data['before_content_encrypted'] = encrypt_data("", self.encryption_key)
                
            if 'after_content' in edit_data:
                edit_data['after_content_encrypted'] = encrypt_data(edit_data['after_content'], self.encryption_key)
                del edit_data['after_content']
            else:
                edit_data['after_content_encrypted'] = encrypt_data("", self.encryption_key)
                
            if 'attachments' in edit_data and edit_data['attachments']:
                edit_data['attachments_encrypted'] = encrypt_data(edit_data['attachments'], self.encryption_key)
                del edit_data['attachments']
            else:
                edit_data['attachments_encrypted'] = None
                
            if 'metadata' in edit_data and edit_data['metadata']:
                edit_data['metadata_encrypted'] = encrypt_data(edit_data['metadata'], self.encryption_key)
                del edit_data['metadata']
            else:
                edit_data['metadata_encrypted'] = None
            
            # Insert edit data into database
            cursor = self.conn.cursor()
            cursor.execute('''
            INSERT INTO message_edits (
                edit_id, message_id, channel_id, guild_id, author_id,
                before_content_encrypted, after_content_encrypted, edit_timestamp,
                attachments_encrypted, metadata_encrypted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                edit_data['edit_id'],
                edit_data['message_id'],
                edit_data['channel_id'],
                edit_data['guild_id'],
                edit_data['author_id'],
                edit_data['before_content_encrypted'],
                edit_data['after_content_encrypted'],
                edit_data['edit_timestamp'],
                edit_data['attachments_encrypted'],
                edit_data['metadata_encrypted']
            ))
            
            # Also update the original message with the new content
            cursor.execute('''
            UPDATE messages
            SET content_encrypted = ?, attachments_encrypted = ?, metadata_encrypted = ?
            WHERE message_id = ?
            ''', (
                edit_data['after_content_encrypted'],
                edit_data['attachments_encrypted'],
                edit_data['metadata_encrypted'],
                edit_data['message_id']
            ))
            
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error storing message edit: {e}", exc_info=True)
            if self.conn:
                self.conn.rollback()
            return False
    
    async def store_message_files(self, message_data):
        """
        Download and store files/images attached to a message or shared via links.
        
        Args:
            message_data (dict): Message data containing the message and any files/links
            
        Returns:
            list: List of downloaded file IDs
        """
        file_ids = []
        
        try:
            message_id = message_data['message_id']
            
            # Process attachments in the message
            if message_data.get('attachments'):
                attachments = message_data['attachments']
                if isinstance(attachments, str):
                    try:
                        attachments = json.loads(attachments)
                    except:
                        # If it's already a string but not JSON, it might be encrypted
                        if isinstance(message_data.get('attachments_encrypted'), str):
                            attachments = json.loads(decrypt_data(
                                self.encryption_key, 
                                message_data['attachments_encrypted']
                            ))
                
                if isinstance(attachments, list):
                    for attachment in attachments:
                        file_id = await self._download_and_store_file(
                            attachment['url'],
                            attachment.get('filename', 'unknown'),
                            message_id,
                            message_data['channel_id'],
                            message_data['guild_id'],
                            message_data['author_id']
                        )
                        if file_id:
                            file_ids.append(file_id)
            
            # Extract and download URLs from message content
            content = message_data.get('content', '')
            if isinstance(content, str):
                # If content is encrypted, decrypt it
                if not content and message_data.get('content_encrypted'):
                    content = decrypt_data(self.encryption_key, message_data['content_encrypted'])
                
                # Extract URLs using a simple regex
                import re
                urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', content)
                
                # Filter for common image and file extensions
                file_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp4', '.webm', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip']
                for url in urls:
                    if any(url.lower().endswith(ext) for ext in file_extensions):
                        # Generate a filename from the URL
                        filename = url.split('/')[-1].split('?')[0]
                        file_id = await self._download_and_store_file(
                            url,
                            filename,
                            message_id,
                            message_data['channel_id'],
                            message_data['guild_id'],
                            message_data['author_id']
                        )
                        if file_id:
                            file_ids.append(file_id)
            
            return file_ids
            
        except Exception as e:
            logger.error(f"Error processing files for message {message_data.get('message_id')}: {e}")
            return file_ids
    
    async def _download_and_store_file(self, url, original_name, message_id, channel_id, guild_id, author_id):
        """
        Download a file from a URL and store it in the files directory.
        
        Args:
            url (str): URL of the file to download
            original_name (str): Original filename
            message_id (str): Associated message ID
            channel_id (str): Channel ID where the file was shared
            guild_id (str): Guild ID where the file was shared
            author_id (str): ID of the user who shared the file
            
        Returns:
            str: File ID if successful, None otherwise
        """
        try:
            # Generate a unique file ID
            file_id = f"file_{hashlib.md5((url + str(datetime.now().timestamp())).encode()).hexdigest()}"
            
            # Determine file extension and sanitize filename
            file_ext = os.path.splitext(original_name)[1].lower()
            if not file_ext:
                # Try to get extension from URL if not in filename
                url_ext = os.path.splitext(url.split('?')[0])[1].lower()
                if url_ext:
                    file_ext = url_ext
                else:
                    file_ext = '.bin'  # Default extension
            
            # Create a sanitized filename
            safe_filename = f"{file_id}{file_ext}"
            file_path = os.path.join(self.files_dir, safe_filename)
            
            # Download the file
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        file_data = await response.read()
                        
                        # Save the file
                        with open(file_path, 'wb') as f:
                            f.write(file_data)
                        
                        # Calculate file hash
                        file_hash = hashlib.sha256(file_data).hexdigest()
                        file_size = len(file_data)
                        
                        # Determine file type
                        file_type = file_ext.lstrip('.').upper()
                        if not file_type:
                            file_type = 'UNKNOWN'
                        
                        # Store file metadata in database
                        cursor = self.conn.cursor()
                        cursor.execute('''
                        INSERT INTO files (
                            file_id, message_id, channel_id, guild_id, author_id,
                            original_name, file_path, file_type, file_size, file_hash,
                            original_url, timestamp, metadata_encrypted
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            file_id,
                            message_id,
                            channel_id,
                            guild_id,
                            author_id,
                            original_name,
                            file_path,
                            file_type,
                            file_size,
                            file_hash,
                            url,
                            datetime.now().isoformat(),
                            None  # No additional metadata encrypted yet
                        ))
                        self.conn.commit()
                        
                        logger.info(f"Downloaded and stored file {file_id} from {url}")
                        return file_id
                    else:
                        logger.warning(f"Failed to download file from {url}, status: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error downloading file from {url}: {e}")
            self.conn.rollback()
            return None
    
    async def download_url(self, url, original_name, message_id, channel_id, guild_id, author_id):
        """
        Download file from a URL and store it in the database.
        This is a wrapper around _download_and_store_file for direct URL downloads.
        
        Args:
            url (str): URL of the file to download
            original_name (str): Original filename
            message_id (str): Associated message ID
            channel_id (str): Channel ID where the file was shared
            guild_id (str): Guild ID where the file was shared
            author_id (str): ID of the user who shared the file
            
        Returns:
            str: File ID if successful, None otherwise
        """
        return await self._download_and_store_file(url, original_name, message_id, channel_id, guild_id, author_id)
    
    def store_reaction(self, reaction_data):
        """
        Store a message reaction in the database.
        
        Args:
            reaction_data (dict): Reaction data to store
            
        Returns:
            bool: Success status
        """
        try:
            # Encrypt metadata if present
            metadata_encrypted = None
            if 'metadata' in reaction_data and reaction_data['metadata']:
                metadata_encrypted = encrypt_data(reaction_data['metadata'], self.encryption_key)
            
            # Insert reaction into database
            cursor = self.conn.cursor()
            cursor.execute('''
            INSERT OR REPLACE INTO reactions (
                reaction_id, message_id, user_id, emoji_name, emoji_id,
                timestamp, metadata_encrypted
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                reaction_data['reaction_id'],
                reaction_data['message_id'],
                reaction_data['user_id'],
                reaction_data['emoji_name'],
                reaction_data.get('emoji_id'),
                reaction_data['timestamp'],
                metadata_encrypted
            ))
            
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error storing reaction: {e}", exc_info=True)
            if self.conn:
                self.conn.rollback()
            return False
    
    def remove_reaction(self, message_id, user_id, emoji_name):
        """
        Remove a reaction from the database.
        
        Args:
            message_id (str): The message ID
            user_id (str): The user ID who reacted
            emoji_name (str): The emoji name
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            reaction_id = f"reaction_{message_id}_{user_id}_{emoji_name}"
            
            cursor = self.conn.cursor()
            cursor.execute('DELETE FROM reactions WHERE reaction_id = ?', (reaction_id,))
            self.conn.commit()
            
            logger.debug(f"Removed reaction {reaction_id} from database")
            return True
            
        except sqlite3.Error as e:
            logger.error(f"Error removing reaction: {e}")
            self.conn.rollback()
            return False
    
    def store_ai_interaction(self, interaction_data):
        """
        Store an AI interaction in the database.
        
        Args:
            interaction_data (dict): AI interaction data to store
            
        Returns:
            bool: Success status
        """
        try:
            # Encrypt sensitive data
            prompt_encrypted = encrypt_data(interaction_data['prompt'], self.encryption_key)
            response_encrypted = encrypt_data(interaction_data['response'], self.encryption_key)
            
            # Encrypt metadata if present
            metadata_encrypted = None
            if 'metadata' in interaction_data and interaction_data['metadata']:
                metadata_encrypted = encrypt_data(interaction_data['metadata'], self.encryption_key)
            
            # Insert interaction into database
            cursor = self.conn.cursor()
            cursor.execute('''
            INSERT OR REPLACE INTO ai_interactions (
                interaction_id, user_id, guild_id, channel_id, model,
                prompt_encrypted, response_encrypted, timestamp,
                tokens_used, execution_time, metadata_encrypted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                interaction_data['interaction_id'],
                interaction_data['user_id'],
                interaction_data['guild_id'],
                interaction_data['channel_id'],
                interaction_data['model'],
                prompt_encrypted,
                response_encrypted,
                interaction_data['timestamp'],
                interaction_data.get('tokens_used'),
                interaction_data.get('execution_time'),
                metadata_encrypted
            ))
            
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error storing AI interaction: {e}", exc_info=True)
            if self.conn:
                self.conn.rollback()
            return False
    
    def get_message(self, message_id):
        """
        Retrieve a message by ID and decrypt sensitive fields.
        
        Args:
            message_id (str): The Discord message ID
            
        Returns:
            dict: The decrypted message data or None if not found
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM messages WHERE message_id = ?', (message_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
                
            # Convert row to dict
            message_data = dict(row)
            
            # Decrypt sensitive fields
            message_data['content'] = decrypt_data(self.encryption_key, message_data['content_encrypted'])
            del message_data['content_encrypted']
            
            if message_data.get('attachments_encrypted'):
                message_data['attachments'] = decrypt_data(self.encryption_key, message_data['attachments_encrypted'])
                del message_data['attachments_encrypted']
            
            if message_data.get('metadata_encrypted'):
                message_data['metadata'] = decrypt_data(self.encryption_key, message_data['metadata_encrypted'])
                del message_data['metadata_encrypted']
                
            message_data['is_bot'] = bool(message_data['is_bot'])
            
            # Get associated files
            cursor.execute('SELECT * FROM files WHERE message_id = ?', (message_id,))
            files = [dict(row) for row in cursor.fetchall()]
            if files:
                message_data['files'] = files
            
            # Get associated reactions
            cursor.execute('SELECT * FROM reactions WHERE message_id = ?', (message_id,))
            reactions = [dict(row) for row in cursor.fetchall()]
            if reactions:
                message_data['reactions'] = reactions
            
            return message_data
        except sqlite3.Error as e:
            logger.error(f"Error retrieving message: {e}")
            raise
    
    def get_ai_interaction(self, interaction_id):
        """
        Retrieve an AI interaction by ID and decrypt sensitive fields.
        
        Args:
            interaction_id (str): The interaction ID
            
        Returns:
            dict: The decrypted interaction data or None if not found
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM ai_interactions WHERE interaction_id = ?', (interaction_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
                
            # Convert row to dict
            interaction_data = dict(row)
            
            # Decrypt sensitive fields
            interaction_data['prompt'] = decrypt_data(self.encryption_key, interaction_data['prompt_encrypted'])
            interaction_data['response'] = decrypt_data(self.encryption_key, interaction_data['response_encrypted'])
            del interaction_data['prompt_encrypted']
            del interaction_data['response_encrypted']
            
            if interaction_data.get('metadata_encrypted'):
                interaction_data['metadata'] = decrypt_data(self.encryption_key, interaction_data['metadata_encrypted'])
                del interaction_data['metadata_encrypted']
                
            return interaction_data
        except sqlite3.Error as e:
            logger.error(f"Error retrieving AI interaction: {e}")
            raise
    
    def get_user_messages(self, user_id, limit=100, offset=0):
        """
        Retrieve messages from a specific user with pagination.
        
        Args:
            user_id (str): The Discord user ID
            limit (int): Maximum number of messages to retrieve
            offset (int): Starting offset for pagination
            
        Returns:
            list: List of decrypted message data
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                'SELECT * FROM messages WHERE author_id = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?',
                (user_id, limit, offset)
            )
            rows = cursor.fetchall()
            
            messages = []
            for row in rows:
                message_data = dict(row)
                
                # Decrypt sensitive fields
                message_data['content'] = decrypt_data(self.encryption_key, message_data['content_encrypted'])
                del message_data['content_encrypted']
                
                if message_data.get('attachments_encrypted'):
                    message_data['attachments'] = decrypt_data(self.encryption_key, message_data['attachments_encrypted'])
                    del message_data['attachments_encrypted']
                
                if message_data.get('metadata_encrypted'):
                    message_data['metadata'] = decrypt_data(self.encryption_key, message_data['metadata_encrypted'])
                    del message_data['metadata_encrypted']
                    
                message_data['is_bot'] = bool(message_data['is_bot'])
                
                # Get associated files
                cursor.execute('SELECT * FROM files WHERE message_id = ?', (message_data['message_id'],))
                files = [dict(row) for row in cursor.fetchall()]
                if files:
                    message_data['files'] = files
                
                # Get associated reactions
                cursor.execute('SELECT * FROM reactions WHERE message_id = ?', (message_data['message_id'],))
                reactions = [dict(row) for row in cursor.fetchall()]
                if reactions:
                    message_data['reactions'] = reactions
                
                messages.append(message_data)
                
            return messages
        except sqlite3.Error as e:
            logger.error(f"Error retrieving user messages: {e}")
            raise
    
    def get_user_ai_interactions(self, user_id, limit=100, offset=0):
        """
        Retrieve AI interactions from a specific user with pagination.
        
        Args:
            user_id (str): The Discord user ID
            limit (int): Maximum number of interactions to retrieve
            offset (int): Starting offset for pagination
            
        Returns:
            list: List of decrypted interaction data
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                'SELECT * FROM ai_interactions WHERE user_id = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?',
                (user_id, limit, offset)
            )
            rows = cursor.fetchall()
            
            interactions = []
            for row in rows:
                interaction_data = dict(row)
                
                # Decrypt sensitive fields
                interaction_data['prompt'] = decrypt_data(self.encryption_key, interaction_data['prompt_encrypted'])
                interaction_data['response'] = decrypt_data(self.encryption_key, interaction_data['response_encrypted'])
                del interaction_data['prompt_encrypted']
                del interaction_data['response_encrypted']
                
                if interaction_data.get('metadata_encrypted'):
                    interaction_data['metadata'] = decrypt_data(self.encryption_key, interaction_data['metadata_encrypted'])
                    del interaction_data['metadata_encrypted']
                    
                interactions.append(interaction_data)
                
            return interactions
        except sqlite3.Error as e:
            logger.error(f"Error retrieving user AI interactions: {e}")
            raise
    
    def get_files(self, filter_criteria=None, limit=100, offset=0):
        """
        Retrieve files with optional filtering.
        
        Args:
            filter_criteria (dict): Optional filters (e.g., {'user_id': '123', 'file_type': 'PNG'})
            limit (int): Maximum number of files to retrieve
            offset (int): Starting offset for pagination
            
        Returns:
            list: List of file data
        """
        try:
            cursor = self.conn.cursor()
            
            # Build query based on filter criteria
            query = 'SELECT * FROM files'
            params = []
            
            if filter_criteria:
                conditions = []
                for key, value in filter_criteria.items():
                    if key in ['file_id', 'message_id', 'channel_id', 'guild_id', 'author_id', 'file_type']:
                        conditions.append(f"{key} = ?")
                        params.append(value)
                
                if conditions:
                    query += ' WHERE ' + ' AND '.join(conditions)
            
            query += ' ORDER BY timestamp DESC LIMIT ? OFFSET ?'
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            files = [dict(row) for row in cursor.fetchall()]
            
            return files
        except sqlite3.Error as e:
            logger.error(f"Error retrieving files: {e}")
            raise
    
    def get_reactions(self, message_id=None, user_id=None, emoji_name=None, limit=100, offset=0):
        """
        Retrieve reactions with optional filtering.
        
        Args:
            message_id (str): Optional message ID filter
            user_id (str): Optional user ID filter
            emoji_name (str): Optional emoji name filter
            limit (int): Maximum number of reactions to retrieve
            offset (int): Starting offset for pagination
            
        Returns:
            list: List of reaction data
        """
        try:
            cursor = self.conn.cursor()
            
            # Build query based on filter criteria
            query = 'SELECT * FROM reactions'
            params = []
            conditions = []
            
            if message_id:
                conditions.append('message_id = ?')
                params.append(message_id)
            
            if user_id:
                conditions.append('user_id = ?')
                params.append(user_id)
            
            if emoji_name:
                conditions.append('emoji_name = ?')
                params.append(emoji_name)
            
            if conditions:
                query += ' WHERE ' + ' AND '.join(conditions)
            
            query += ' ORDER BY timestamp DESC LIMIT ? OFFSET ?'
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            reactions = [dict(row) for row in cursor.fetchall()]
            
            # Decrypt metadata if present
            for reaction in reactions:
                if reaction.get('metadata_encrypted'):
                    reaction['metadata'] = decrypt_data(self.encryption_key, reaction['metadata_encrypted'])
                    del reaction['metadata_encrypted']
            
            return reactions
        except sqlite3.Error as e:
            logger.error(f"Error retrieving reactions: {e}")
            raise
    
    def search_messages(self, query, limit=100):
        """
        Search messages (note: this requires decrypting all messages to search, which is inefficient).
        This is a simplified implementation that should be optimized for production use.
        
        Args:
            query (str): The search query
            limit (int): Maximum number of results
            
        Returns:
            list: List of matching messages
        """
        # In a real implementation, you would use a separate search index or implement
        # more efficient search. This is a basic example that's not optimized.
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM messages ORDER BY timestamp DESC')
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                if len(results) >= limit:
                    break
                    
                message_data = dict(row)
                
                # Decrypt content to search
                try:
                    content = decrypt_data(self.encryption_key, message_data['content_encrypted'])
                    
                    # Check if query is in content
                    if query.lower() in content.lower():
                        # Construct result with decrypted fields
                        message_data['content'] = content
                        del message_data['content_encrypted']
                        
                        if message_data.get('attachments_encrypted'):
                            message_data['attachments'] = decrypt_data(
                                self.encryption_key, 
                                message_data['attachments_encrypted']
                            )
                            del message_data['attachments_encrypted']
                        
                        if message_data.get('metadata_encrypted'):
                            message_data['metadata'] = decrypt_data(
                                self.encryption_key, 
                                message_data['metadata_encrypted']
                            )
                            del message_data['metadata_encrypted']
                            
                        message_data['is_bot'] = bool(message_data['is_bot'])
                        
                        # Get associated files
                        cursor.execute('SELECT * FROM files WHERE message_id = ?', (message_data['message_id'],))
                        files = [dict(row) for row in cursor.fetchall()]
                        if files:
                            message_data['files'] = files
                        
                        # Get associated reactions
                        cursor.execute('SELECT * FROM reactions WHERE message_id = ?', (message_data['message_id'],))
                        reactions = [dict(row) for row in cursor.fetchall()]
                        if reactions:
                            message_data['reactions'] = reactions
                            
                        results.append(message_data)
                except Exception as e:
                    logger.error(f"Error decrypting message during search: {e}")
                    continue
                
            return results
        except sqlite3.Error as e:
            logger.error(f"Error searching messages: {e}")
            raise
            
    # Dashboard-related methods
    
    def get_statistics(self):
        """
        Get database statistics for the dashboard.
        
        Returns:
            dict: Statistics about the database contents
        """
        try:
            cursor = self.conn.cursor()
            
            stats = {
                "total_messages": 0,
                "total_ai_interactions": 0,
                "total_files": 0,
                "total_reactions": 0,
                "unique_users": 0,
                "file_types": {},
                "reaction_counts": {},
                "daily_message_counts": {},
                "daily_ai_interaction_counts": {}
            }
            
            # Get counts
            cursor.execute('SELECT COUNT(*) FROM messages')
            stats["total_messages"] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM ai_interactions')
            stats["total_ai_interactions"] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM files')
            stats["total_files"] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM reactions')
            stats["total_reactions"] = cursor.fetchone()[0]
            
            # Get unique users
            cursor.execute('SELECT COUNT(DISTINCT author_id) FROM messages')
            stats["unique_users"] = cursor.fetchone()[0]
            
            # Get file type distribution
            cursor.execute('SELECT file_type, COUNT(*) as count FROM files GROUP BY file_type ORDER BY count DESC')
            for row in cursor.fetchall():
                stats["file_types"][row['file_type']] = row['count']
            
            # Get reaction distribution
            cursor.execute('SELECT emoji_name, COUNT(*) as count FROM reactions GROUP BY emoji_name ORDER BY count DESC LIMIT 20')
            for row in cursor.fetchall():
                stats["reaction_counts"][row['emoji_name']] = row['count']
            
            # Get daily message counts (last 30 days)
            cursor.execute('''
            SELECT substr(timestamp, 1, 10) as date, COUNT(*) as count 
            FROM messages 
            WHERE timestamp >= date('now', '-30 days')
            GROUP BY date
            ORDER BY date
            ''')
            for row in cursor.fetchall():
                stats["daily_message_counts"][row['date']] = row['count']
            
            # Get daily AI interaction counts (last 30 days)
            cursor.execute('''
            SELECT substr(timestamp, 1, 10) as date, COUNT(*) as count 
            FROM ai_interactions 
            WHERE timestamp >= date('now', '-30 days')
            GROUP BY date
            ORDER BY date
            ''')
            for row in cursor.fetchall():
                stats["daily_ai_interaction_counts"][row['date']] = row['count']
            
            return stats
            
        except sqlite3.Error as e:
            logger.error(f"Error generating statistics: {e}")
            raise
    
    # AI content analysis methods
    
    async def get_file_info(self, file_id):
        """
        Get information about a stored file.
        
        Args:
            file_id (str): ID of the file to retrieve
            
        Returns:
            dict: File information including path and metadata, or None if not found
        """
        try:
            # Use the queue to prevent concurrent access issues
            return await self.queue.execute(lambda: self._get_file_info_sync(file_id))
        except Exception as e:
            logger.error(f"Error retrieving file info: {e}")
            return None
    
    def _get_file_info_sync(self, file_id):
        """Synchronous implementation of get_file_info for use with the database queue."""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM files WHERE file_id = ?', (file_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
                
            # Convert row to dict
            file_info = dict(row)
            
            # If there's encrypted metadata, decrypt it
            if file_info.get('metadata_encrypted'):
                try:
                    file_info['metadata'] = json.loads(decrypt_data(
                        self.encryption_key, 
                        file_info['metadata_encrypted']
                    ))
                    del file_info['metadata_encrypted']
                except Exception as e:
                    logger.error(f"Error decrypting file metadata: {e}")
                    file_info['metadata'] = {}
            else:
                file_info['metadata'] = {}
                
            return file_info
        except sqlite3.Error as e:
            logger.error(f"Error retrieving file info: {e}")
            return None
    
    async def update_file_metadata(self, file_id, metadata_dict):
        """
        Update metadata for a file with AI analysis.
        
        Args:
            file_id (str): ID of the file to update
            metadata_dict (dict): New metadata to add to the file
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Use the queue to prevent concurrent access issues
            return await self.queue.execute(
                lambda: self._update_file_metadata_sync(file_id, metadata_dict)
            )
        except Exception as e:
            logger.error(f"Error updating file metadata: {e}")
            return False
    
    def _update_file_metadata_sync(self, file_id, metadata_dict):
        """
        Update file metadata in the database - synchronous version.
        
        Args:
            file_id (str): The file ID to update
            metadata_dict (dict): New metadata to merge with existing metadata
            
        Returns:
            bool: Success status
        """
        try:
            # Get current metadata
            cursor = self.conn.cursor()
            cursor.execute("SELECT metadata_encrypted FROM files WHERE file_id = ?", (file_id,))
            row = cursor.fetchone()
            
            if not row:
                logger.error(f"File {file_id} not found when updating metadata")
                return False
                
            # Decrypt current metadata
            current_metadata = {}
            if row['metadata_encrypted']:
                try:
                    current_metadata = json.loads(decrypt_data(self.encryption_key, row['metadata_encrypted']))
                except Exception as e:
                    logger.error(f"Error decrypting metadata: {e}")
                    # Continue with empty metadata
            
            # Merge with new metadata
            updated_metadata = {**current_metadata, **metadata_dict}
            
            # Encrypt updated metadata
            metadata_encrypted = encrypt_data(json.dumps(updated_metadata), self.encryption_key)
            
            # Update database
            cursor.execute(
                "UPDATE files SET metadata_encrypted = ? WHERE file_id = ?",
                (metadata_encrypted, file_id)
            )
            
            self.conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error updating file metadata: {e}", exc_info=True)
            if self.conn:
                self.conn.rollback()
            return False
    
    def get_recent_messages(self, limit=25, channel_id=None, guild_id=None):
        """
        Get most recent messages with optimal O(log n) performance using indexes.
        
        Args:
            limit (int): Maximum number of messages to return
            channel_id (str, optional): Filter by specific channel
            guild_id (str, optional): Filter by specific guild
            
        Returns:
            list: Recent messages with decrypted content
        """
        try:
            cursor = self.conn.cursor()
            
            # Build query based on filter criteria
            query = 'SELECT * FROM messages'
            params = []
            
            conditions = []
            if channel_id:
                conditions.append('channel_id = ?')
                params.append(channel_id)
            
            if guild_id:
                conditions.append('guild_id = ?')
                params.append(guild_id)
            
            if conditions:
                query += ' WHERE ' + ' AND '.join(conditions)
            
            # Use timestamp index for O(log n) complexity
            query += ' ORDER BY timestamp DESC LIMIT ?'
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            messages = []
            for row in rows:
                message_data = dict(row)
                
                # Decrypt sensitive fields
                message_data['content'] = decrypt_data(self.encryption_key, message_data['content_encrypted'])
                del message_data['content_encrypted']
                
                if message_data.get('attachments_encrypted'):
                    message_data['attachments'] = decrypt_data(self.encryption_key, message_data['attachments_encrypted'])
                    del message_data['attachments_encrypted']
                
                if message_data.get('metadata_encrypted'):
                    message_data['metadata'] = decrypt_data(self.encryption_key, message_data['metadata_encrypted'])
                    del message_data['metadata_encrypted']
                    
                message_data['is_bot'] = bool(message_data['is_bot'])
                
                # Get associated files (using message_id index for O(log n) lookup)
                cursor.execute('SELECT * FROM files WHERE message_id = ?', (message_data['message_id'],))
                files = [dict(row) for row in cursor.fetchall()]
                if files:
                    message_data['files'] = files
                
                # Get associated reactions (using message_id index for O(log n) lookup)
                cursor.execute('SELECT * FROM reactions WHERE message_id = ?', (message_data['message_id'],))
                reactions = [dict(row) for row in cursor.fetchall()]
                if reactions:
                    message_data['reactions'] = reactions
                
                messages.append(message_data)
                
            return messages
            
        except sqlite3.Error as e:
            logger.error(f"Error retrieving recent messages: {e}")
            return []
    
    def get_active_users(self, days=7, limit=10):
        """
        Get most active users over a specific period.
        Uses indexed queries for O(log n) performance.
        
        Args:
            days (int): Number of days to look back
            limit (int): Maximum number of users to return
            
        Returns:
            list: User activity data
        """
        try:
            cursor = self.conn.cursor()
            
            # Calculate date range using SQLite date functions
            cursor.execute('''
            SELECT author_id, author_name, COUNT(*) as message_count 
            FROM messages 
            WHERE timestamp >= date('now', ?) 
            GROUP BY author_id 
            ORDER BY message_count DESC 
            LIMIT ?
            ''', (f'-{days} days', limit))
            
            rows = cursor.fetchall()
            
            active_users = []
            for row in rows:
                user_data = {
                    'user_id': row['author_id'],
                    'username': row['author_name'],
                    'message_count': row['message_count'],
                    'ai_interactions': 0,
                    'file_uploads': 0
                }
                
                # Get AI interaction count (using indexed user_id for O(log n) lookup)
                cursor.execute('''
                SELECT COUNT(*) as count 
                FROM ai_interactions 
                WHERE user_id = ? AND timestamp >= date('now', ?)
                ''', (row['author_id'], f'-{days} days'))
                user_data['ai_interactions'] = cursor.fetchone()['count']
                
                # Get file upload count (using indexed author_id for O(log n) lookup)
                cursor.execute('''
                SELECT COUNT(*) as count 
                FROM files 
                WHERE author_id = ? AND timestamp >= date('now', ?)
                ''', (row['author_id'], f'-{days} days'))
                user_data['file_uploads'] = cursor.fetchone()['count']
                
                active_users.append(user_data)
                
            return active_users
            
        except sqlite3.Error as e:
            logger.error(f"Error retrieving active users: {e}")
            return []
    
    def search_messages(self, query, filter_criteria=None, limit=100, offset=0):
        """
        Search messages with optimized performance.
        
        Args:
            query (str): The search query
            filter_criteria (dict): Optional filters like user_id, channel_id, etc.
            limit (int): Maximum number of results
            offset (int): Pagination offset
            
        Returns:
            list: List of matching messages
        """
        try:
            cursor = self.conn.cursor()
            
            # Using indexed fields first to narrow down the search space
            base_conditions = []
            params = []
            
            if filter_criteria:
                # Apply all indexed filters first for O(log n) narrowing
                if filter_criteria.get('author_id'):
                    base_conditions.append('author_id = ?')
                    params.append(filter_criteria['author_id'])
                
                if filter_criteria.get('channel_id'):
                    base_conditions.append('channel_id = ?')
                    params.append(filter_criteria['channel_id'])
                
                if filter_criteria.get('guild_id'):
                    base_conditions.append('guild_id = ?')
                    params.append(filter_criteria['guild_id'])
                
                # Add date range filter if provided (using timestamp index)
                if filter_criteria.get('start_date'):
                    base_conditions.append('timestamp >= ?')
                    params.append(filter_criteria['start_date'])
                
                if filter_criteria.get('end_date'):
                    base_conditions.append('timestamp <= ?')
                    params.append(filter_criteria['end_date'])
            
            # Build initial query that uses indexes for efficient filtering
            if base_conditions:
                indexed_query = 'SELECT * FROM messages WHERE ' + ' AND '.join(base_conditions)
            else:
                indexed_query = 'SELECT * FROM messages'
                
            # Add order by for consistent pagination
            indexed_query += ' ORDER BY timestamp DESC'
            
            # Use LIMIT and OFFSET for pagination
            full_query = indexed_query + ' LIMIT ? OFFSET ?'
            params.extend([limit, offset])
            
            cursor.execute(full_query, params)
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                message_data = dict(row)
                
                # Decrypt content to search
                try:
                    content = decrypt_data(self.encryption_key, message_data['content_encrypted'])
                    
                    # If query is empty or matches content, include in results
                    if not query or query.lower() in content.lower():
                        # Include this message in results
                        message_data['content'] = content
                        del message_data['content_encrypted']
                        
                        if message_data.get('attachments_encrypted'):
                            message_data['attachments'] = decrypt_data(
                                self.encryption_key, 
                                message_data['attachments_encrypted']
                            )
                            del message_data['attachments_encrypted']
                        
                        if message_data.get('metadata_encrypted'):
                            message_data['metadata'] = decrypt_data(
                                self.encryption_key, 
                                message_data['metadata_encrypted']
                            )
                            del message_data['metadata_encrypted']
                            
                        message_data['is_bot'] = bool(message_data['is_bot'])
                        
                        # Get associated files
                        cursor.execute('SELECT * FROM files WHERE message_id = ?', (message_data['message_id'],))
                        files = [dict(row) for row in cursor.fetchall()]
                        if files:
                            message_data['files'] = files
                        
                        # Get associated reactions
                        cursor.execute('SELECT * FROM reactions WHERE message_id = ?', (message_data['message_id'],))
                        reactions = [dict(row) for row in cursor.fetchall()]
                        if reactions:
                            message_data['reactions'] = reactions
                            
                        results.append(message_data)
                except Exception as e:
                    logger.error(f"Error decrypting message during search: {e}")
                    continue
            
            return results
        except sqlite3.Error as e:
            logger.error(f"Error searching messages: {e}")
            return []
    
    def get_guild_statistics(self, guild_id):
        """
        Get statistics for a specific Discord guild with O(log n) lookup performance.
        
        Args:
            guild_id (str): Discord guild ID
            
        Returns:
            dict: Guild statistics
        """
        try:
            cursor = self.conn.cursor()
            
            stats = {
                "total_messages": 0,
                "total_users": 0,
                "total_channels": 0,
                "total_files": 0,
                "daily_activity": {},
                "user_rankings": {},
                "channel_rankings": {},
                "file_types": {}
            }
            
            # Get total messages (indexed lookup)
            cursor.execute('SELECT COUNT(*) FROM messages WHERE guild_id = ?', (guild_id,))
            stats["total_messages"] = cursor.fetchone()[0]
            
            # Get unique users (indexed lookup)
            cursor.execute('SELECT COUNT(DISTINCT author_id) FROM messages WHERE guild_id = ?', (guild_id,))
            stats["total_users"] = cursor.fetchone()[0]
            
            # Get unique channels (indexed lookup)
            cursor.execute('SELECT COUNT(DISTINCT channel_id) FROM messages WHERE guild_id = ?', (guild_id,))
            stats["total_channels"] = cursor.fetchone()[0]
            
            # Get total files (indexed lookup)
            cursor.execute('SELECT COUNT(*) FROM files WHERE guild_id = ?', (guild_id,))
            stats["total_files"] = cursor.fetchone()[0]
            
            # Get daily activity (last 30 days)
            cursor.execute('''
            SELECT substr(timestamp, 1, 10) as date, COUNT(*) as count 
            FROM messages 
            WHERE guild_id = ? AND timestamp >= date('now', '-30 days')
            GROUP BY date
            ORDER BY date
            ''', (guild_id,))
            
            for row in cursor.fetchall():
                stats["daily_activity"][row['date']] = row['count']
            
            # Get top 10 users by message count
            cursor.execute('''
            SELECT author_id, author_name, COUNT(*) as count 
            FROM messages 
            WHERE guild_id = ?
            GROUP BY author_id 
            ORDER BY count DESC 
            LIMIT 10
            ''', (guild_id,))
            
            for row in cursor.fetchall():
                stats["user_rankings"][row['author_id']] = {
                    "name": row['author_name'],
                    "message_count": row['count']
                }
            
            # Get top 10 channels by message count
            cursor.execute('''
            SELECT channel_id, COUNT(*) as count 
            FROM messages 
            WHERE guild_id = ?
            GROUP BY channel_id 
            ORDER BY count DESC 
            LIMIT 10
            ''', (guild_id,))
            
            for row in cursor.fetchall():
                stats["channel_rankings"][row['channel_id']] = {
                    "message_count": row['count']
                }
            
            # Get file type distribution
            cursor.execute('''
            SELECT file_type, COUNT(*) as count 
            FROM files 
            WHERE guild_id = ?
            GROUP BY file_type 
            ORDER BY count DESC
            ''', (guild_id,))
            
            for row in cursor.fetchall():
                stats["file_types"][row['file_type']] = row['count']
            
            return stats
            
        except sqlite3.Error as e:
            logger.error(f"Error retrieving guild statistics: {e}")
            return {}