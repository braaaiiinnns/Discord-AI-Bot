import sqlite3
import os
import json
import logging
import requests
import hashlib
import aiohttp
import asyncio
import threading
import uuid
from datetime import datetime, timedelta
from utils.ncrypt import encrypt_data, decrypt_data
from typing import List, Dict, Any, Optional, Union, Callable
from queue import Queue, Empty
from threading import Thread, Lock
from config.config import FILES_DIRECTORY # Import FILES_DIRECTORY
import time

logger = logging.getLogger('discord_bot')

# Add the missing get_db_path function
def get_db_path(db_name: str) -> str:
    """
    Get the path for a database file.
    
    Args:
        db_name: Name of the database file
        
    Returns:
        Full path to the database file in the data/db directory
    """
    # Ensure the database name has .db extension
    if not db_name.endswith('.db'):
        db_name = f"{db_name}.db"
        
    # Create the database directory if it doesn't exist
    db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'db')
    os.makedirs(db_dir, exist_ok=True)
    
    # Return the full path
    return os.path.join(db_dir, db_name)

# Store database connections per thread
thread_local = threading.local()

# Add a connection pool
class ConnectionPool:
    def __init__(self, db_path: str, max_connections: int = 5):
        self.db_path = db_path
        self.max_connections = max_connections
        self.connections = []
        self.in_use = set()
        self.lock = asyncio.Lock()
        
    async def get_connection(self):
        async with self.lock:
            # Check if there's an available connection
            available = [conn for conn in self.connections if conn not in self.in_use]
            if available:
                conn = available[0]
                self.in_use.add(conn)
                return conn
                
            # Create a new connection if below the limit
            if len(self.connections) < self.max_connections:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                self.connections.append(conn)
                self.in_use.add(conn)
                return conn
                
            # Wait for a connection to become available
            while True:
                await asyncio.sleep(0.1)
                available = [conn for conn in self.connections if conn not in self.in_use]
                if available:
                    conn = available[0]
                    self.in_use.add(conn)
                    return conn
    
    async def release_connection(self, conn):
        async with self.lock:
            if conn in self.in_use:
                self.in_use.remove(conn)
    
    async def close_all(self):
        async with self.lock:
            for conn in self.connections:
                conn.close()
            self.connections = []
            self.in_use = set()

class DatabaseQueue:
    """Thread-safe queue for database operations to prevent concurrent access issues with SQLite."""
    
    def __init__(self, max_workers=1):
        """
        Initialize the database queue.
        
        Args:
            max_workers (int): Maximum number of worker threads (usually 1 for SQLite)
        """
        logger.debug(f"Initializing DatabaseQueue with {max_workers} workers.")
        self.queue = Queue()
        self.lock = Lock()
        self.workers = []
        self.running = True
        
        # Start worker threads
        for i in range(max_workers):
            worker = Thread(target=self._worker_loop, daemon=True, name=f"DBWorker-{i}")
            worker.start()
            self.workers.append(worker)
            logger.debug(f"Started DBWorker thread {i}.")
        logger.debug("DatabaseQueue initialized.")
    
    def _worker_loop(self):
        """Worker thread that processes database operations from the queue."""
        logger.debug(f"DBWorker {threading.current_thread().name} started loop.")
        while self.running:
            try:
                try:
                    operation, future = self.queue.get(timeout=1.0)
                    logger.debug(f"DBWorker {threading.current_thread().name} got operation from queue.")
                except Empty:
                    continue
                
                try:
                    logger.debug(f"DBWorker {threading.current_thread().name} executing operation.")
                    result = operation()
                    if not future.done():
                        future.set_result(result)
                    logger.debug(f"DBWorker {threading.current_thread().name} finished operation successfully.")
                except Exception as e:
                    logger.error(f"DBWorker {threading.current_thread().name} encountered error during operation: {e}", exc_info=True)
                    if not future.done():
                        future.set_exception(e)
                finally:
                    self.queue.task_done()
            except Exception as e:
                logger.error(f"Error in database worker {threading.current_thread().name}: {e}", exc_info=True)
        logger.debug(f"DBWorker {threading.current_thread().name} stopping loop.")
    
    async def execute(self, operation: Callable) -> Any:
        """
        Add an operation to the queue and wait for its result.
        
        Args:
            operation: Callable that performs a database operation
            
        Returns:
            The result of the operation
        """
        logger.debug(f"Adding operation {operation.__name__ if hasattr(operation, '__name__') else 'lambda'} to DB queue.")
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        
        self.queue.put((operation, future))
        logger.debug("Operation added to queue. Waiting for future.")
        
        result = await future
        logger.debug("Future completed. Returning result.")
        return result
    
    def stop(self):
        """Stop all worker threads."""
        logger.debug("Stopping DatabaseQueue workers.")
        self.running = False
        
        for i, worker in enumerate(self.workers):
            if worker.is_alive():
                logger.debug(f"Joining DBWorker thread {i}...")
                worker.join(timeout=5.0)
                if worker.is_alive():
                    logger.warning(f"DBWorker thread {i} did not terminate gracefully.")
                else:
                    logger.debug(f"DBWorker thread {i} joined.")
            else:
                logger.debug(f"DBWorker thread {i} was already stopped.")
        logger.debug("DatabaseQueue stopped.")

class UnifiedDatabase:
    """
    Unified database for message storage and AI interactions storage.
    Uses a single SQLite database with multiple tables.
    """
    
    def __init__(self, db_path: str, encryption_key: str = None, create_tables: bool = True):
        """
        Initialize the database.
        
        Args:
            db_path (str): Path to the database file
            encryption_key (str, optional): Encryption key for sensitive data
            create_tables (bool): Whether to create tables if they don't exist
        """
        self.db_path = db_path
        self.encryption_key = encryption_key
        self.track_bot_messages = True  # Set to False to skip logging bot messages
        self.discord_client = None
        self.connection_pool = ConnectionPool(db_path, max_connections=10)
        
        # Create database directory if it doesn't exist
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # Store whether to create tables for later async initialization
        self.should_create_tables = create_tables
        
    async def initialize(self):
        """Asynchronously initialize the database."""
        if self.should_create_tables:
            await self._create_tables()
        
    async def _get_connection(self):
        """Get a connection from the pool"""
        return await self.connection_pool.get_connection()
        
    async def _release_connection(self, conn):
        """Release a connection back to the pool"""
        await self.connection_pool.release_connection(conn)
    
    def _connect(self):
        """Establish a connection to the database."""
        thread_name = threading.current_thread().name
        logger.debug(f"Attempting to connect to database for thread: {thread_name}")
        try:
            if not hasattr(self.local_storage, 'conn') or self.local_storage.conn is None:
                logger.debug(f"No existing connection found for thread {thread_name}. Creating new connection.")
                self.local_storage.conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self.local_storage.conn.row_factory = sqlite3.Row
                logger.debug(f"New connection created for thread {thread_name}.")
            else:
                logger.debug(f"Using existing connection for thread {thread_name}.")
            
            if threading.current_thread() is threading.main_thread() and not self.conn:
                logger.debug("Assigning connection to self.conn for main thread.")
                self.conn = self.local_storage.conn
            
            return self.local_storage.conn
        except sqlite3.Error as e:
            logger.error(f"Failed to connect to database for thread {thread_name}: {e}", exc_info=True)
            raise
    
    async def cursor(self):
        """
        Get a cursor from the current thread's database connection.
        
        Returns:
            sqlite3.Cursor: A database cursor
        """
        logger.debug("Getting database cursor from current connection.")
        conn = await self._get_connection()
        return conn.cursor()
    
    async def close(self):
        """Close the database connection pool."""
        logger.info("Closing database connection pool...")
        try:
            if hasattr(self, 'connection_pool') and self.connection_pool:
                await self.connection_pool.close_all()
                logger.info("Database connection pool closed.")
            else:
                logger.warning("Connection pool not found or already closed.")
        except Exception as e:
            logger.error(f"Error closing connection pool: {e}", exc_info=True)

    async def _create_tables(self):
        """Create necessary tables if they don't exist."""
        logger.debug("Executing _create_tables.")
        try:
            conn = await self._get_connection()
            cursor = await self.cursor()
            
            logger.debug("Creating table: messages")
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
            
            logger.debug("Creating table: ai_interactions")
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_interactions (
                interaction_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                user_name TEXT NOT NULL,
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
            
            logger.debug("Creating table: files")
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
            
            logger.debug("Creating table: reactions")
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
            
            logger.debug("Creating table: message_edits")
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS message_edits (
                edit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                author_id TEXT NOT NULL,
                original_content_encrypted TEXT,
                new_content_encrypted TEXT,
                edit_timestamp TEXT NOT NULL,
                FOREIGN KEY (message_id) REFERENCES messages (message_id)
            )
            ''')
            
            logger.debug("Creating table: channels")
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                channel_id TEXT PRIMARY KEY,
                guild_id TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                channel_type TEXT NOT NULL,
                last_update TEXT NOT NULL
            )
            ''')
            
            logger.debug("Creating indexes...")
            # Message indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_author ON messages (author_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_guild ON messages (guild_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages (channel_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages (timestamp)')
            
            # AI interaction indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_user ON ai_interactions (user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_guild ON ai_interactions (guild_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_model ON ai_interactions (model)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_timestamp ON ai_interactions (timestamp)')
            
            # File indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_message ON files (message_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_author ON files (author_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_type ON files (file_type)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_hash ON files (file_hash)')
            
            # Reaction indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_reactions_message ON reactions (message_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_reactions_user ON reactions (user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_reactions_emoji ON reactions (emoji_name)')
            
            # Edit indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_edits_message ON message_edits (message_id)')
            
            # Channel indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_channels_guild ON channels (guild_id)')
            
            conn.commit()
            logger.debug("Tables and indexes created/verified successfully.")
        except sqlite3.Error as e:
            logger.error(f"Error creating tables: {e}", exc_info=True)
            raise
    
    # Message-related methods
    async def store_message(self, message_data: Dict[str, Any]) -> bool:
        """
        Store a message in the database.
        
        Args:
            message_data (dict): Message data
            
        Returns:
            bool: Success status
        """
        try:
            conn = await self._get_connection()
            
            # If the message is from a bot and we're not tracking bot messages, skip it
            if message_data.get('is_bot', False) and not self.track_bot_messages:
                await self._release_connection(conn)
                return True
                
            cursor = conn.cursor()
            
            # Encrypt the content before storing
            content_encrypted = encrypt_data(self.encryption_key, message_data['content'])
            
            # Encrypt attachments if any
            attachments_encrypted = None
            if 'attachments' in message_data and message_data['attachments']:
                if isinstance(message_data['attachments'], list):
                    attachments_json = json.dumps(message_data['attachments'])
                else:
                    attachments_json = message_data['attachments']
                attachments_encrypted = encrypt_data(self.encryption_key, attachments_json)
                
            # Use prepared statement for better security
            cursor.execute('''
            INSERT INTO messages (
                message_id, channel_id, guild_id, author_id, author_name, 
                content_encrypted, timestamp, attachments_encrypted, message_type, is_bot
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(message_id) DO UPDATE SET
                content_encrypted = excluded.content_encrypted
            ''', (
                message_data['message_id'],
                message_data['channel_id'],
                message_data['guild_id'],
                message_data['author_id'],
                message_data['author_name'],
                content_encrypted,
                message_data['timestamp'],
                attachments_encrypted,
                message_data['message_type'],
                message_data['is_bot']
            ))
            
            # Insert attachments if any
            if 'attachments' in message_data and message_data['attachments']:
                for attachment in message_data['attachments']:
                    cursor.execute('''
                    INSERT INTO attachments (
                        attachment_id, message_id, filename, url, 
                        proxy_url, size, height, width, content_type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(attachment_id) DO NOTHING
                    ''', (
                        attachment['id'],
                        message_data['message_id'],
                        attachment['filename'],
                        attachment['url'],
                        attachment['proxy_url'],
                        attachment['size'],
                        attachment['height'] or 0,
                        attachment['width'] or 0,
                        attachment.get('content_type', '')
                    ))
            
            conn.commit()
            await self._release_connection(conn)
            return True
            
        except Exception as e:
            logger.error(f"Error storing message {message_data.get('message_id', 'unknown')}: {e}", exc_info=True)
            return False
            
    async def store_message_files(self, message_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Download and store files attached to a message.
        
        Args:
            message_data (dict): Message data containing attachments
            
        Returns:
            List[Dict[str, Any]]: List of stored file metadata
        """
        stored_files_metadata = []
        if 'attachments' not in message_data or not message_data['attachments']:
            logger.debug(f"No attachments found for message {message_data['message_id']}.")
            return stored_files_metadata

        attachments = message_data['attachments']
        if isinstance(attachments, str):
            try:
                attachments = json.loads(attachments)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse attachments JSON for message {message_data['message_id']}")
                return stored_files_metadata
                
        logger.debug(f"Processing {len(attachments)} attachments for message {message_data['message_id']}.")
        
        async with aiohttp.ClientSession() as session:
            for attachment in attachments:
                file_id = attachment['id']
                original_name = attachment['filename']
                file_url = attachment['url']
                file_type = attachment.get('content_type', 'application/octet-stream')
                file_size = attachment['size']
                timestamp = message_data['timestamp']
                
                logger.debug(f"Processing attachment: {original_name} ({file_id}) from URL: {file_url}")

                try:
                    async with session.get(file_url) as response:
                        if response.status == 200:
                            file_content = await response.read()
                            file_hash = hashlib.sha256(file_content).hexdigest()
                            
                            # Determine file path
                            file_extension = os.path.splitext(original_name)[1]
                            file_name = f"{file_hash}{file_extension}"
                            file_path = os.path.join(self.files_dir, file_name)
                            
                            # Save file if it doesn't already exist (based on hash)
                            if not os.path.exists(file_path):
                                with open(file_path, 'wb') as f:
                                    f.write(file_content)
                                logger.debug(f"Saved file {original_name} to {file_path}")
                            else:
                                logger.debug(f"File {original_name} with hash {file_hash} already exists at {file_path}. Skipping save.")

                            # Store file metadata in the database via queue
                            metadata_encrypted = None # Add metadata encryption if needed later
                            
                            # Operation to store file metadata
                            success = await self.store_file_metadata(
                                file_id, message_data['message_id'], message_data['channel_id'],
                                message_data['guild_id'], message_data['author_id'],
                                original_name, file_path, file_type, file_size,
                                file_hash, file_url, timestamp, None
                            )

                            if success:
                                stored_files_metadata.append({
                                    'file_id': file_id,
                                    'original_name': original_name,
                                    'file_path': file_path,
                                    'file_type': file_type,
                                    'file_size': file_size,
                                    'file_hash': file_hash,
                                    'original_url': file_url
                                })
                                logger.debug(f"Successfully stored metadata for file {original_name} ({file_id}).")
                            else:
                                logger.error(f"Failed to store metadata for file {original_name} ({file_id}).")
                        else:
                            logger.error(f"Failed to download file {original_name} from {file_url}. Status: {response.status}")
                except Exception as e:
                    logger.error(f"Error processing attachment {original_name}: {e}", exc_info=True)
        
        return stored_files_metadata
    
    async def store_file_metadata(self, file_id, message_id, channel_id, guild_id, author_id, 
                                  original_name, file_path, file_type, file_size, file_hash, 
                                  original_url, timestamp, metadata) -> bool:
        """
        Store file metadata in the database.
        
        Args:
            Various file metadata parameters
            
        Returns:
            bool: Success status
        """
        try:
            metadata_encrypted = None
            if metadata:
                metadata_json = metadata if isinstance(metadata, str) else json.dumps(metadata)
                metadata_encrypted = encrypt_data(self.encryption_key, metadata_json)
                
            conn = await self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
            INSERT OR REPLACE INTO files (
                file_id, message_id, channel_id, guild_id, author_id, 
                original_name, file_path, file_type, file_size, file_hash, 
                original_url, timestamp, metadata_encrypted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                file_id, message_id, channel_id, guild_id, author_id,
                original_name, file_path, file_type, file_size, file_hash,
                original_url, timestamp, metadata_encrypted
            ))
            conn.commit()
            await self._release_connection(conn)
            logger.debug(f"Stored metadata for file {original_name} ({file_id}).")
            return True
        except Exception as e:
            logger.error(f"Error storing file metadata for {original_name} ({file_id}): {e}", exc_info=True)
            # Try to rollback and release connection if it exists
            try:
                if 'conn' in locals():
                    conn.rollback()
                    await self._release_connection(conn)
            except:
                pass
            return False
    
    async def store_message_edit(self, edit_data: Dict[str, Any]) -> bool:
        """
        Store a message edit event in the database.
        
        Args:
            edit_data (dict): Data about the message edit
            
        Returns:
            bool: Success status
        """
        try:
            logger.debug(f"Storing message edit for message {edit_data['message_id']}.")
            original_content_encrypted = encrypt_data(self.encryption_key, edit_data['original_content'])
            new_content_encrypted = encrypt_data(self.encryption_key, edit_data['new_content'])
            
            conn = await self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO message_edits (
                message_id, channel_id, guild_id, author_id,
                original_content_encrypted, new_content_encrypted, edit_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                edit_data['message_id'],
                edit_data['channel_id'],
                edit_data['guild_id'],
                edit_data['author_id'],
                original_content_encrypted,
                new_content_encrypted,
                edit_data['edit_timestamp']
            ))
            
            conn.commit()
            await self._release_connection(conn)
            logger.debug(f"Message edit for {edit_data['message_id']} stored successfully.")
            return True
        except Exception as e:
            logger.error(f"Error storing message edit: {e}", exc_info=True)
            try:
                if 'conn' in locals():
                    conn.rollback()
                    await self._release_connection(conn)
            except:
                pass
            return False
    
    async def store_channel(self, channel_data: Dict[str, Any]) -> bool:
        """
        Store or update a channel in the database.
        
        Args:
            channel_data (dict): Channel data
            
        Returns:
            bool: Success status
        """
        def _store_channel_sync():
            try:
                logger.debug(f"Storing channel {channel_data['channel_id']}.")
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                INSERT OR REPLACE INTO channels (
                    channel_id, guild_id, channel_name, channel_type, last_update
                ) VALUES (?, ?, ?, ?, ?)
                ''', (
                    channel_data['channel_id'],
                    channel_data['guild_id'],
                    channel_data['channel_name'],
                    channel_data['channel_type'],
                    channel_data['last_update']
                ))
                
                conn.commit()
                logger.debug(f"Channel {channel_data['channel_id']} stored successfully.")
                return True
            except Exception as e:
                logger.error(f"Error storing channel: {e}", exc_info=True)
                conn = self._get_connection()
                conn.rollback()
                return False
                
        return await self.queue.execute(_store_channel_sync)
    
    # AI interaction methods
    async def store_ai_interaction(self, interaction_data: Dict[str, Any]) -> bool:
        """
        Store an AI interaction in the database.
        
        Args:
            interaction_data (dict): AI interaction data
            
        Returns:
            bool: Success status
        """
        def _store_ai_interaction_sync():
            try:
                logger.debug(f"Storing AI interaction {interaction_data['interaction_id']}.")
                prompt_encrypted = encrypt_data(self.encryption_key, interaction_data['prompt'])
                response_encrypted = encrypt_data(self.encryption_key, interaction_data['response'])
                
                metadata_encrypted = None
                if 'metadata' in interaction_data and interaction_data['metadata']:
                    metadata_json = interaction_data['metadata'] if isinstance(interaction_data['metadata'], str) else json.dumps(interaction_data['metadata'])
                    metadata_encrypted = encrypt_data(self.encryption_key, metadata_json)
                
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                INSERT OR REPLACE INTO ai_interactions (
                    interaction_id, user_id, user_name, guild_id, channel_id, model,
                    prompt_encrypted, response_encrypted, timestamp,
                    tokens_used, execution_time, metadata_encrypted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    interaction_data['interaction_id'],
                    interaction_data['user_id'],
                    interaction_data.get('user_name', 'Unknown'),  # Handle cases where user_name might be missing
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
                
                conn.commit()
                logger.debug(f"AI interaction {interaction_data['interaction_id']} stored successfully.")
                return True
            except Exception as e:
                logger.error(f"Error storing AI interaction: {e}", exc_info=True)
                conn = self._get_connection()
                conn.rollback()
                return False
                
        return await self.queue.execute(_store_ai_interaction_sync)
    
    # Query methods
    async def get_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a message from the database.
        
        Args:
            message_id (str): The ID of the message
            
        Returns:
            Optional[Dict[str, Any]]: The message data or None
        """
        def _get_message_sync():
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM messages WHERE message_id = ?", (message_id,))
                row = cursor.fetchone()
                
                if not row:
                    logger.debug(f"No message found with ID {message_id}")
                    return None
                    
                # Convert row to dict and decrypt fields
                message = dict(row)
                
                if message.get('content_encrypted'):
                    message['content'] = decrypt_data(self.encryption_key, message['content_encrypted'])
                    del message['content_encrypted']
                
                if message.get('attachments_encrypted'):
                    decrypted = decrypt_data(self.encryption_key, message['attachments_encrypted'])
                    message['attachments'] = json.loads(decrypted) if decrypted else []
                    del message['attachments_encrypted']
                else:
                    message['attachments'] = []
                    
                if message.get('metadata_encrypted'):
                    decrypted = decrypt_data(self.encryption_key, message['metadata_encrypted'])
                    message['metadata'] = json.loads(decrypted) if decrypted else {}
                    del message['metadata_encrypted']
                else:
                    message['metadata'] = {}
                    
                return message
            except Exception as e:
                logger.error(f"Error getting message {message_id}: {e}", exc_info=True)
                return None
                
        return await self.queue.execute(_get_message_sync)
    
    async def get_ai_interaction(self, interaction_id: str) -> Optional[Dict[str, Any]]:
        """
        Get an AI interaction from the database.
        
        Args:
            interaction_id (str): The ID of the interaction
            
        Returns:
            Optional[Dict[str, Any]]: The interaction data or None
        """
        def _get_ai_interaction_sync():
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM ai_interactions WHERE interaction_id = ?", (interaction_id,))
                row = cursor.fetchone()
                
                if not row:
                    logger.debug(f"No AI interaction found with ID {interaction_id}")
                    return None
                    
                # Convert row to dict and decrypt fields
                interaction = dict(row)
                
                if interaction.get('prompt_encrypted'):
                    interaction['prompt'] = decrypt_data(self.encryption_key, interaction['prompt_encrypted'])
                    del interaction['prompt_encrypted']
                
                if interaction.get('response_encrypted'):
                    interaction['response'] = decrypt_data(self.encryption_key, interaction['response_encrypted'])
                    del interaction['response_encrypted']
                    
                if interaction.get('metadata_encrypted'):
                    decrypted = decrypt_data(self.encryption_key, interaction['metadata_encrypted'])
                    interaction['metadata'] = json.loads(decrypted) if decrypted else {}
                    del interaction['metadata_encrypted']
                else:
                    interaction['metadata'] = {}
                    
                return interaction
            except Exception as e:
                logger.error(f"Error getting AI interaction {interaction_id}: {e}", exc_info=True)
                return None
                
        return await self.queue.execute(_get_ai_interaction_sync)
    
    async def get_user_messages(self, user_id: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get messages from a specific user.
        
        Args:
            user_id (str): The user's ID
            limit (int): Maximum number of messages
            offset (int): Offset for pagination
            
        Returns:
            List[Dict[str, Any]]: List of message data
        """
        def _get_user_messages_sync():
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM messages WHERE author_id = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                    (user_id, limit, offset)
                )
                rows = cursor.fetchall()
                
                messages = []
                for row in rows:
                    message = dict(row)
                    
                    # Decrypt message content
                    if message.get('content_encrypted'):
                        message['content'] = decrypt_data(self.encryption_key, message['content_encrypted'])
                        del message['content_encrypted']
                    
                    # Decrypt attachments
                    if message.get('attachments_encrypted'):
                        decrypted = decrypt_data(self.encryption_key, message['attachments_encrypted'])
                        message['attachments'] = json.loads(decrypted) if decrypted else []
                        del message['attachments_encrypted']
                    else:
                        message['attachments'] = []
                        
                    # Decrypt metadata
                    if message.get('metadata_encrypted'):
                        decrypted = decrypt_data(self.encryption_key, message['metadata_encrypted'])
                        message['metadata'] = json.loads(decrypted) if decrypted else {}
                        del message['metadata_encrypted']
                    else:
                        message['metadata'] = {}
                        
                    messages.append(message)
                    
                return messages
            except Exception as e:
                logger.error(f"Error getting messages for user {user_id}: {e}", exc_info=True)
                return []
                
        return await self.queue.execute(_get_user_messages_sync)
    
    async def get_user_ai_interactions(self, user_id: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get AI interactions from a specific user.
        
        Args:
            user_id (str): The user's ID
            limit (int): Maximum number of interactions
            offset (int): Offset for pagination
            
        Returns:
            List[Dict[str, Any]]: List of interaction data
        """
        def _get_user_ai_interactions_sync():
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM ai_interactions WHERE user_id = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                    (user_id, limit, offset)
                )
                rows = cursor.fetchall()
                
                interactions = []
                for row in rows:
                    interaction = dict(row)
                    
                    # Decrypt prompt
                    if interaction.get('prompt_encrypted'):
                        interaction['prompt'] = decrypt_data(self.encryption_key, interaction['prompt_encrypted'])
                        del interaction['prompt_encrypted']
                    
                    # Decrypt response
                    if interaction.get('response_encrypted'):
                        interaction['response'] = decrypt_data(self.encryption_key, interaction['response_encrypted'])
                        del interaction['response_encrypted']
                        
                    # Decrypt metadata
                    if interaction.get('metadata_encrypted'):
                        decrypted = decrypt_data(self.encryption_key, interaction['metadata_encrypted'])
                        interaction['metadata'] = json.loads(decrypted) if decrypted else {}
                        del interaction['metadata_encrypted']
                    else:
                        interaction['metadata'] = {}
                        
                    interactions.append(interaction)
                    
                return interactions
            except Exception as e:
                logger.error(f"Error getting AI interactions for user {user_id}: {e}", exc_info=True)
                return []
                
        return await self.queue.execute(_get_user_ai_interactions_sync)
    
    async def get_all_channels(self) -> List[Dict[str, Any]]:
        """
        Get all channels from the database.
        
        Returns:
            List[Dict[str, Any]]: List of channel data
        """
        def _get_all_channels_sync():
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                
                # Check if the channels table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='channels'")
                if cursor.fetchone() is None:
                    logger.warning("Channels table does not exist")
                    return []
                
                cursor.execute("SELECT * FROM channels")
                rows = cursor.fetchall()
                
                return [dict(row) for row in rows]
            except Exception as e:
                logger.error(f"Error getting channels: {e}", exc_info=True)
                return []
                
        return await self.queue.execute(_get_all_channels_sync)
    
    async def get_stats(self, days: int = 30, guild_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get statistics from the database.
        
        Args:
            days (int): Number of days to include in stats
            guild_id (Optional[str]): Specific guild ID to filter by
            
        Returns:
            Dict[str, Any]: Statistics data
        """
        def _get_stats_sync():
            try:
                stats = {
                    "message_count": 0,
                    "user_count": 0,
                    "ai_count": 0,
                    "channels_count": 0,
                    "files_count": 0,
                    "daily_messages": [],
                    "daily_ai": [],
                    "model_distribution": [],
                    "top_users": []
                }
                
                conn = self._get_connection()
                cursor = conn.cursor()
                
                # Add WHERE clause if guild_id is provided
                guild_filter = "WHERE guild_id = ?" if guild_id else ""
                params = [guild_id] if guild_id else []
                
                # Count messages
                if guild_id:
                    cursor.execute(f"SELECT COUNT(*) FROM messages {guild_filter}", params)
                else:
                    cursor.execute("SELECT COUNT(*) FROM messages")
                stats["message_count"] = cursor.fetchone()[0]
                
                # Count unique users
                if guild_id:
                    cursor.execute(f"SELECT COUNT(DISTINCT author_id) FROM messages {guild_filter}", params)
                else:
                    cursor.execute("SELECT COUNT(DISTINCT author_id) FROM messages")
                stats["user_count"] = cursor.fetchone()[0]
                
                # Count AI interactions
                try:
                    if guild_id:
                        cursor.execute(f"SELECT COUNT(*) FROM ai_interactions {guild_filter}", params)
                    else:
                        cursor.execute("SELECT COUNT(*) FROM ai_interactions")
                    stats["ai_count"] = cursor.fetchone()[0]
                except sqlite3.OperationalError:
                    # Table might not exist yet
                    stats["ai_count"] = 0
                
                # Count channels
                if guild_id:
                    cursor.execute(f"SELECT COUNT(DISTINCT channel_id) FROM messages {guild_filter}", params)
                else:
                    cursor.execute("SELECT COUNT(DISTINCT channel_id) FROM messages")
                stats["channels_count"] = cursor.fetchone()[0]
                
                # Count files
                try:
                    if guild_id:
                        cursor.execute(f"SELECT COUNT(*) FROM files {guild_filter}", params)
                    else:
                        cursor.execute("SELECT COUNT(*) FROM files")
                    stats["files_count"] = cursor.fetchone()[0]
                except sqlite3.OperationalError:
                    stats["files_count"] = 0
                
                # Daily message counts
                days_ago = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
                if guild_id:
                    query = f"""
                        SELECT DATE(timestamp) as date, COUNT(*) as count 
                        FROM messages 
                        {guild_filter} AND DATE(timestamp) >= ?
                        GROUP BY date
                        ORDER BY date
                    """
                    cursor.execute(query, params + [days_ago])
                else:
                    query = """
                        SELECT DATE(timestamp) as date, COUNT(*) as count 
                        FROM messages 
                        WHERE DATE(timestamp) >= ?
                        GROUP BY date
                        ORDER BY date
                    """
                    cursor.execute(query, [days_ago])
                
                stats["daily_messages"] = [{"date": row[0], "count": row[1]} for row in cursor.fetchall()]
                
                # Daily AI interactions
                try:
                    if guild_id:
                        query = f"""
                            SELECT DATE(timestamp) as date, COUNT(*) as count 
                            FROM ai_interactions 
                            {guild_filter} AND DATE(timestamp) >= ?
                            GROUP BY date
                            ORDER BY date
                        """
                        cursor.execute(query, params + [days_ago])
                    else:
                        query = """
                            SELECT DATE(timestamp) as date, COUNT(*) as count 
                            FROM ai_interactions 
                            WHERE DATE(timestamp) >= ?
                            GROUP BY date
                            ORDER BY date
                        """
                        cursor.execute(query, [days_ago])
                    
                    stats["daily_ai"] = [{"date": row[0], "count": row[1]} for row in cursor.fetchall()]
                except sqlite3.OperationalError:
                    stats["daily_ai"] = []
                
                # AI model distribution
                try:
                    if guild_id:
                        query = f"""
                            SELECT model, COUNT(*) as count 
                            FROM ai_interactions 
                            {guild_filter}
                            GROUP BY model
                            ORDER BY count DESC
                        """
                        cursor.execute(query, params)
                    else:
                        query = """
                            SELECT model, COUNT(*) as count 
                            FROM ai_interactions 
                            GROUP BY model
                            ORDER BY count DESC
                        """
                        cursor.execute(query)
                    
                    stats["model_distribution"] = [{"model": row[0], "count": row[1]} for row in cursor.fetchall()]
                except sqlite3.OperationalError:
                    stats["model_distribution"] = []
                
                # Top users by message count
                if guild_id:
                    query = f"""
                        SELECT author_name, COUNT(*) as count 
                        FROM messages 
                        {guild_filter}
                        GROUP BY author_id
                        ORDER BY count DESC
                        LIMIT 10
                    """
                    cursor.execute(query, params)
                else:
                    query = """
                        SELECT author_name, COUNT(*) as count 
                        FROM messages 
                        GROUP BY author_id
                        ORDER BY count DESC
                        LIMIT 10
                    """
                    cursor.execute(query)
                
                stats["top_users"] = [{"name": row[0], "count": row[1]} for row in cursor.fetchall()]
                
                return stats
            except Exception as e:
                logger.error(f"Error getting stats: {e}", exc_info=True)
                return {"error": str(e)}
                
        return await self.queue.execute(_get_stats_sync)

    async def migrate_from_old_databases(self, messages_db_path, ai_interactions_db_path, source_encryption_key=None):
        """
        Migrate data from old separate database files to this unified database.
        
        Args:
            messages_db_path (str): Path to old messages database
            ai_interactions_db_path (str): Path to old AI interactions database
            source_encryption_key (str, optional): Encryption key used in the source databases, if different from current
            
        Returns:
            Dict[str, Any]: Migration statistics
        """
        stats = {
            "messages_migrated": 0,
            "ai_interactions_migrated": 0,
            "files_migrated": 0,
            "reactions_migrated": 0,
            "edits_migrated": 0,
            "errors": []
        }
        
        # Use source encryption key if provided, otherwise use the current key
        decrypt_key = source_encryption_key if source_encryption_key else self.encryption_key
        
        try:
            # Migrate messages database
            if os.path.exists(messages_db_path):
                logger.info(f"Migrating messages from {messages_db_path}")
                
                # Connect to old messages database
                msgs_conn = sqlite3.connect(messages_db_path)
                msgs_conn.row_factory = sqlite3.Row
                msgs_cursor = msgs_conn.cursor()
                
                # Get all messages
                msgs_cursor.execute("SELECT * FROM messages")
                messages = [dict(row) for row in msgs_cursor.fetchall()]
                
                # Store each message in the new database
                for msg in messages:
                    try:
                        # Convert to our expected format
                        message_data = {
                            'message_id': msg['message_id'],
                            'channel_id': msg['channel_id'],
                            'guild_id': msg['guild_id'],
                            'author_id': msg['author_id'],
                            'author_name': msg['author_name'],
                            'content': decrypt_data(decrypt_key, msg['content_encrypted']),
                            'timestamp': msg['timestamp'],
                            'attachments': decrypt_data(decrypt_key, msg.get('attachments_encrypted', '')) if msg.get('attachments_encrypted') else None,
                            'message_type': msg['message_type'],
                            'is_bot': msg['is_bot'],
                            'metadata': decrypt_data(decrypt_key, msg.get('metadata_encrypted', '')) if msg.get('metadata_encrypted') else None
                        }
                        
                        await self.store_message(message_data)
                        stats["messages_migrated"] += 1
                    except Exception as e:
                        error_msg = f"Error migrating message {msg.get('message_id')}: {e}"
                        logger.error(error_msg)
                        stats["errors"].append(error_msg)
                
                # Migrate files
                try:
                    msgs_cursor.execute("SELECT * FROM files")
                    files = [dict(row) for row in msgs_cursor.fetchall()]
                    
                    for file in files:
                        try:
                            metadata = decrypt_data(decrypt_key, file.get('metadata_encrypted', '')) if file.get('metadata_encrypted') else None
                            
                            await self.store_file_metadata(
                                file['file_id'], 
                                file['message_id'],
                                file['channel_id'],
                                file['guild_id'],
                                file['author_id'],
                                file['original_name'],
                                file['file_path'],
                                file['file_type'],
                                file['file_size'],
                                file['file_hash'],
                                file.get('original_url'),
                                file['timestamp'],
                                metadata
                            )
                            stats["files_migrated"] += 1
                        except Exception as e:
                            error_msg = f"Error migrating file {file.get('file_id')}: {e}"
                            logger.error(error_msg)
                            stats["errors"].append(error_msg)
                except sqlite3.OperationalError:
                    logger.warning("Files table not found in old messages database")
                
                # Migrate reactions
                try:
                    msgs_cursor.execute("SELECT * FROM reactions")
                    reactions = [dict(row) for row in msgs_cursor.fetchall()]
                    
                    for reaction in reactions:
                        try:
                            conn = self._get_connection()
                            cursor = conn.cursor()
                            
                            metadata_encrypted = reaction.get('metadata_encrypted')
                            
                            cursor.execute('''
                            INSERT OR REPLACE INTO reactions (
                                reaction_id, message_id, user_id, emoji_name, emoji_id, timestamp, metadata_encrypted
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                reaction['reaction_id'],
                                reaction['message_id'],
                                reaction['user_id'],
                                reaction['emoji_name'],
                                reaction.get('emoji_id'),
                                reaction['timestamp'],
                                metadata_encrypted
                            ))
                            
                            conn.commit()
                            stats["reactions_migrated"] += 1
                        except Exception as e:
                            error_msg = f"Error migrating reaction {reaction.get('reaction_id')}: {e}"
                            logger.error(error_msg)
                            stats["errors"].append(error_msg)
                except sqlite3.OperationalError:
                    logger.warning("Reactions table not found in old messages database")
                
                # Migrate message edits
                try:
                    msgs_cursor.execute("SELECT * FROM message_edits")
                    edits = [dict(row) for row in msgs_cursor.fetchall()]
                    
                    for edit in edits:
                        try:
                            conn = self._get_connection()
                            cursor = conn.cursor()
                            
                            cursor.execute('''
                            INSERT INTO message_edits (
                                message_id, channel_id, guild_id, author_id,
                                original_content_encrypted, new_content_encrypted, edit_timestamp
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                edit['message_id'],
                                edit['channel_id'],
                                edit['guild_id'],
                                edit['author_id'],
                                edit.get('original_content_encrypted'),
                                edit.get('new_content_encrypted'),
                                edit.get('edit_timestamp')
                            ))
                            
                            conn.commit()
                            stats["edits_migrated"] += 1
                        except Exception as e:
                            error_msg = f"Error migrating message edit: {e}"
                            logger.error(error_msg)
                            stats["errors"].append(error_msg)
                except sqlite3.OperationalError:
                    logger.warning("Message_edits table not found in old messages database")
                
                msgs_conn.close()
            
            # Migrate AI interactions database
            if os.path.exists(ai_interactions_db_path):
                logger.info(f"Migrating AI interactions from {ai_interactions_db_path}")
                
                # Connect to old AI interactions database
                ai_conn = sqlite3.connect(ai_interactions_db_path)
                ai_conn.row_factory = sqlite3.Row
                ai_cursor = ai_conn.cursor()
                
                # Get all AI interactions
                ai_cursor.execute("SELECT * FROM ai_interactions")
                interactions = [dict(row) for row in ai_cursor.fetchall()]
                
                # Store each interaction in the new database
                for ai in interactions:
                    try:
                        # Convert to our expected format
                        interaction_data = {
                            'interaction_id': ai['interaction_id'],
                            'user_id': ai['user_id'],
                            'user_name': ai.get('user_name', 'Unknown'),  # Handle cases where user_name might be missing
                            'guild_id': ai['guild_id'],
                            'channel_id': ai['channel_id'],
                            'model': ai['model'],
                            'prompt': decrypt_data(decrypt_key, ai['prompt_encrypted']),
                            'response': decrypt_data(decrypt_key, ai['response_encrypted']),
                            'timestamp': ai['timestamp'],
                            'tokens_used': ai.get('tokens_used'),
                            'execution_time': ai.get('execution_time'),
                            'metadata': decrypt_data(decrypt_key, ai.get('metadata_encrypted', '')) if ai.get('metadata_encrypted') else None
                        }
                        
                        await self.store_ai_interaction(interaction_data)
                        stats["ai_interactions_migrated"] += 1
                    except Exception as e:
                        error_msg = f"Error migrating AI interaction {ai.get('interaction_id')}: {e}"
                        logger.error(error_msg)
                        stats["errors"].append(error_msg)
                
                ai_conn.close()
            
            return stats
        except Exception as e:
            error_msg = f"Error during migration: {e}"
            logger.error(error_msg, exc_info=True)
            stats["errors"].append(error_msg)
            return stats

    def set_discord_client(self, client):
        """Set a reference to the Discord client for additional context"""
        self.discord_client = client
        logger.debug("Discord client reference set in database.")
    
    async def get_dashboard_summary(self, filter_criteria: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Get summary statistics for the dashboard.
        
        Args:
            filter_criteria (Optional[Dict[str, str]]): Optional filters (e.g., guild_id)
            
        Returns:
            Dict[str, Any]: Summary statistics
        """
        return await self.get_stats(30, filter_criteria.get('guild_id') if filter_criteria else None)
    
    async def get_message_stats(self, filter_criteria: Optional[Dict[str, str]] = None, days: int = 30) -> Dict[str, Any]:
        """
        Get message statistics for the dashboard.
        
        Args:
            filter_criteria (Optional[Dict[str, str]]): Optional filters (e.g., guild_id)
            days (int): Number of days to include
            
        Returns:
            Dict[str, Any]: Message statistics
        """
        def _get_message_stats_sync():
            try:
                stats = {
                    "daily_messages": [],
                    "messages_by_channel": [],
                    "hourly_activity": []
                }
                
                conn = self._get_connection()
                cursor = conn.cursor()
                
                guild_id = filter_criteria.get('guild_id') if filter_criteria else None
                guild_filter = "WHERE guild_id = ?" if guild_id else ""
                params = [guild_id] if guild_id else []
                
                # Get daily message counts
                days_ago = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
                if guild_id:
                    query = f"""
                        SELECT DATE(timestamp) as date, COUNT(*) as count 
                        FROM messages 
                        {guild_filter} AND DATE(timestamp) >= ?
                        GROUP BY date
                        ORDER BY date
                    """
                    cursor.execute(query, params + [days_ago])
                else:
                    query = """
                        SELECT DATE(timestamp) as date, COUNT(*) as count 
                        FROM messages 
                        WHERE DATE(timestamp) >= ?
                        GROUP BY date
                        ORDER BY date
                    """
                    cursor.execute(query, [days_ago])
                
                stats["daily_messages"] = [{"date": row[0], "count": row[1]} for row in cursor.fetchall()]
                
                # Get messages by channel
                if guild_id:
                    query = f"""
                        SELECT c.channel_name, COUNT(m.message_id) as count
                        FROM messages m
                        LEFT JOIN channels c ON m.channel_id = c.channel_id
                        WHERE m.guild_id = ?
                        GROUP BY m.channel_id
                        ORDER BY count DESC
                        LIMIT 10
                    """
                    cursor.execute(query, [guild_id])
                else:
                    query = """
                        SELECT c.channel_name, COUNT(m.message_id) as count
                        FROM messages m
                        LEFT JOIN channels c ON m.channel_id = c.channel_id
                        GROUP BY m.channel_id
                        ORDER BY count DESC
                        LIMIT 10
                    """
                    cursor.execute(query)
                
                channel_results = cursor.fetchall()
                stats["messages_by_channel"] = []
                
                for row in channel_results:
                    channel_name = row[0] if row[0] else "Unknown Channel"
                    stats["messages_by_channel"].append({
                        "channel_name": channel_name,
                        "count": row[1]
                    })
                
                # Get hourly activity patterns
                if guild_id:
                    query = f"""
                        SELECT 
                            strftime('%H', timestamp) as hour,
                            CASE strftime('%w', timestamp)
                                WHEN '0' THEN 'Sunday'
                                WHEN '1' THEN 'Monday'
                                WHEN '2' THEN 'Tuesday'
                                WHEN '3' THEN 'Wednesday'
                                WHEN '4' THEN 'Thursday'
                                WHEN '5' THEN 'Friday'
                                WHEN '6' THEN 'Saturday'
                            END as weekday,
                            COUNT(*) as count
                        FROM messages
                        WHERE guild_id = ? AND DATE(timestamp) >= ?
                        GROUP BY hour, weekday
                        ORDER BY weekday, hour
                    """
                    cursor.execute(query, [guild_id, days_ago])
                else:
                    query = """
                        SELECT 
                            strftime('%H', timestamp) as hour,
                            CASE strftime('%w', timestamp)
                                WHEN '0' THEN 'Sunday'
                                WHEN '1' THEN 'Monday'
                                WHEN '2' THEN 'Tuesday'
                                WHEN '3' THEN 'Wednesday'
                                WHEN '4' THEN 'Thursday'
                                WHEN '5' THEN 'Friday'
                                WHEN '6' THEN 'Saturday'
                            END as weekday,
                            COUNT(*) as count
                        FROM messages
                        WHERE DATE(timestamp) >= ?
                        GROUP BY hour, weekday
                        ORDER BY weekday, hour
                    """
                    cursor.execute(query, [days_ago])
                
                stats["hourly_activity"] = [{"hour": int(row[0]), "weekday": row[1], "count": row[2]} for row in cursor.fetchall()]
                
                return stats
            except Exception as e:
                logger.error(f"Error getting message stats: {e}", exc_info=True)
                return {"error": str(e)}
                
        return await self.queue.execute(_get_message_stats_sync)
        
    async def get_user_stats(self, filter_criteria: Optional[Dict[str, str]] = None, limit: int = 10) -> Dict[str, Any]:
        """
        Get user statistics for the dashboard.
        
        Args:
            filter_criteria (Optional[Dict[str, str]]): Optional filters (e.g., guild_id)
            limit (int): Number of users to include
            
        Returns:
            Dict[str, Any]: User statistics
        """
        def _get_user_stats_sync():
            try:
                stats = {
                    "active_users": [],
                    "user_roles": [],
                    "user_growth": []
                }
                
                conn = self._get_connection()
                cursor = conn.cursor()
                
                guild_id = filter_criteria.get('guild_id') if filter_criteria else None
                guild_filter = "WHERE guild_id = ?" if guild_id else ""
                params = [guild_id] if guild_id else []
                
                # Get active users
                if guild_id:
                    query = f"""
                        SELECT author_name, COUNT(*) as message_count 
                        FROM messages 
                        {guild_filter} 
                        GROUP BY author_id
                        ORDER BY message_count DESC
                        LIMIT ?
                    """
                    cursor.execute(query, params + [limit])
                else:
                    query = """
                        SELECT author_name, COUNT(*) as message_count 
                        FROM messages 
                        GROUP BY author_id
                        ORDER BY message_count DESC
                        LIMIT ?
                    """
                    cursor.execute(query, [limit])
                
                stats["active_users"] = [{"username": row[0], "message_count": row[1]} for row in cursor.fetchall()]
                
                # If we have a Discord client reference, try to get role information
                if guild_id and self.discord_client:
                    try:
                        guild = self.discord_client.get_guild(int(guild_id))
                        if guild:
                            role_counts = {}
                            for member in guild.members:
                                for role in member.roles:
                                    if role.name != "@everyone":
                                        if role.name in role_counts:
                                            role_counts[role.name] += 1
                                        else:
                                            role_counts[role.name] = 1
                            
                            stats["user_roles"] = [{"role": role, "count": count} 
                                                for role, count in sorted(role_counts.items(), 
                                                                        key=lambda x: x[1], 
                                                                        reverse=True)][:10]
                    except Exception as e:
                        logger.error(f"Error getting role information: {e}", exc_info=True)
                
                # Get user growth over time (weekly)
                days_ago_30 = (datetime.now() - timedelta(days=35)).strftime('%Y-%m-%d')
                
                if guild_id:
                    query = f"""
                        SELECT 
                            strftime('%Y-%m-%d', DATE(timestamp, 'weekday 0', '-7 days')) as week_start,
                            COUNT(DISTINCT author_id) as user_count
                        FROM messages
                        WHERE guild_id = ? AND DATE(timestamp) >= ?
                        GROUP BY week_start
                        ORDER BY week_start
                    """
                    cursor.execute(query, [guild_id, days_ago_30])
                else:
                    query = """
                        SELECT 
                            strftime('%Y-%m-%d', DATE(timestamp, 'weekday 0', '-7 days')) as week_start,
                            COUNT(DISTINCT author_id) as user_count
                        FROM messages
                        WHERE DATE(timestamp) >= ?
                        GROUP BY week_start
                        ORDER BY week_start
                    """
                    cursor.execute(query, [days_ago_30])
                
                stats["user_growth"] = [{"date": row[0], "count": row[1]} for row in cursor.fetchall()]
                
                return stats
            except Exception as e:
                logger.error(f"Error getting user stats: {e}", exc_info=True)
                return {"error": str(e)}
                
        return await self.queue.execute(_get_user_stats_sync)
        
    async def get_ai_stats(self, filter_criteria: Optional[Dict[str, str]] = None, days: int = 30) -> Dict[str, Any]:
        """
        Get AI interaction statistics for the dashboard.
        
        Args:
            filter_criteria (Optional[Dict[str, str]]): Optional filters (e.g., guild_id)
            days (int): Number of days to include
            
        Returns:
            Dict[str, Any]: AI statistics
        """
        def _get_ai_stats_sync():
            try:
                stats = {
                    "ai_models": [],
                    "ai_daily": [],
                    "ai_users": []
                }
                
                conn = self._get_connection()
                cursor = conn.cursor()
                
                # Check if the ai_interactions table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ai_interactions'")
                if cursor.fetchone() is None:
                    logger.warning("AI interactions table does not exist")
                    return stats
                
                guild_id = filter_criteria.get('guild_id') if filter_criteria else None
                guild_filter = "WHERE guild_id = ?" if guild_id else ""
                params = [guild_id] if guild_id else []
                
                # Get model usage counts
                if guild_id:
                    query = f"""
                        SELECT model, COUNT(*) as count 
                        FROM ai_interactions 
                        {guild_filter}
                        GROUP BY model
                        ORDER BY count DESC
                    """
                    cursor.execute(query, params)
                else:
                    query = """
                        SELECT model, COUNT(*) as count 
                        FROM ai_interactions 
                        GROUP BY model
                        ORDER BY count DESC
                    """
                    cursor.execute(query)
                
                stats["ai_models"] = [{"model": row[0], "count": row[1]} for row in cursor.fetchall()]
                
                # Get daily AI interaction counts
                days_ago = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
                if guild_id:
                    query = f"""
                        SELECT DATE(timestamp) as date, COUNT(*) as count 
                        FROM ai_interactions 
                        {guild_filter} AND DATE(timestamp) >= ?
                        GROUP BY date
                        ORDER BY date
                    """
                    cursor.execute(query, params + [days_ago])
                else:
                    query = """
                        SELECT DATE(timestamp) as date, COUNT(*) as count 
                        FROM ai_interactions 
                        WHERE DATE(timestamp) >= ?
                        GROUP BY date
                        ORDER BY date
                    """
                    cursor.execute(query, [days_ago])
                
                stats["ai_daily"] = [{"date": row[0], "count": row[1]} for row in cursor.fetchall()]
                
                # Get top users of AI
                if guild_id:
                    query = f"""
                        SELECT user_name, COUNT(*) as count 
                        FROM ai_interactions 
                        {guild_filter}
                        GROUP BY user_id
                        ORDER BY count DESC
                        LIMIT 10
                    """
                    cursor.execute(query, params)
                else:
                    query = """
                        SELECT user_name, COUNT(*) as count 
                        FROM ai_interactions 
                        GROUP BY user_id
                        ORDER BY count DESC
                        LIMIT 10
                    """
                    cursor.execute(query)
                
                stats["ai_users"] = [{"username": row[0], "count": row[1]} for row in cursor.fetchall()]
                
                return stats
            except Exception as e:
                logger.error(f"Error getting AI stats: {e}", exc_info=True)
                return {"error": str(e)}
                
        return await self.queue.execute(_get_ai_stats_sync)
        
    async def get_all_messages(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Get all messages from the database with pagination.
        
        Args:
            limit (int): Maximum number of messages to return
            
        Returns:
            List[Dict[str, Any]]: List of message data
        """
        def _get_all_messages_sync():
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT m.*, c.channel_name 
                    FROM messages m
                    LEFT JOIN channels c ON m.channel_id = c.channel_id
                    ORDER BY m.timestamp DESC
                    LIMIT ?
                """, [limit])
                rows = cursor.fetchall()
                
                messages = []
                for row in dict_factory(cursor, rows):
                    # Decrypt sensitive fields
                    if 'content_encrypted' in row and row['content_encrypted']:
                        row['content'] = decrypt_data(self.encryption_key, row['content_encrypted'])
                        del row['content_encrypted']
                    
                    if 'attachments_encrypted' in row and row['attachments_encrypted']:
                        decrypted = decrypt_data(self.encryption_key, row['attachments_encrypted'])
                        try:
                            row['attachments'] = json.loads(decrypted) if decrypted else []
                        except:
                            row['attachments'] = []
                        del row['attachments_encrypted']
                    else:
                        row['attachments'] = []
                        
                    if 'metadata_encrypted' in row and row['metadata_encrypted']:
                        decrypted = decrypt_data(self.encryption_key, row['metadata_encrypted'])
                        try:
                            row['metadata'] = json.loads(decrypted) if decrypted else {}
                        except:
                            row['metadata'] = {}
                        del row['metadata_encrypted']
                    else:
                        row['metadata'] = {}
                        
                    messages.append(row)
                    
                return messages
            except Exception as e:
                logger.error(f"Error getting all messages: {e}", exc_info=True)
                return []
                
        return await self.queue.execute(_get_all_messages_sync)
        
    async def get_all_ai_interactions(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Get all AI interactions from the database with pagination.
        
        Args:
            limit (int): Maximum number of interactions to return
            
        Returns:
            List[Dict[str, Any]]: List of AI interaction data
        """
        def _get_all_ai_interactions_sync():
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                
                # Check if the ai_interactions table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ai_interactions'")
                if cursor.fetchone() is None:
                    logger.warning("AI interactions table does not exist")
                    return []
                
                cursor.execute("""
                    SELECT * FROM ai_interactions
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, [limit])
                rows = cursor.fetchall()
                
                interactions = []
                for row in dict_factory(cursor, rows):
                    # Decrypt sensitive fields
                    if 'prompt_encrypted' in row and row['prompt_encrypted']:
                        row['prompt'] = decrypt_data(self.encryption_key, row['prompt_encrypted'])
                        del row['prompt_encrypted']
                    
                    if 'response_encrypted' in row and row['response_encrypted']:
                        row['response'] = decrypt_data(self.encryption_key, row['response_encrypted'])
                        del row['response_encrypted']
                        
                    if 'metadata_encrypted' in row and row['metadata_encrypted']:
                        decrypted = decrypt_data(self.encryption_key, row['metadata_encrypted'])
                        try:
                            row['metadata'] = json.loads(decrypted) if decrypted else {}
                        except:
                            row['metadata'] = {}
                        del row['metadata_encrypted']
                    else:
                        row['metadata'] = {}
                        
                    interactions.append(row)
                    
                return interactions
            except Exception as e:
                logger.error(f"Error getting all AI interactions: {e}", exc_info=True)
                return []
                
        return await self.queue.execute(_get_all_ai_interactions_sync)
        
    async def get_all_files(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get all files from the database."""
        def _get_all_files_sync():
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                
                # Check if the files table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='files'")
                if cursor.fetchone() is None:
                    logger.warning("Files table does not exist")
                    return []
                
                cursor.execute("""
                    SELECT * FROM files
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, [limit])
                rows = cursor.fetchall()
                
                files = []
                for row in dict_factory(cursor, rows):
                    if 'metadata_encrypted' in row and row['metadata_encrypted']:
                        decrypted = decrypt_data(self.encryption_key, row['metadata_encrypted'])
                        try:
                            row['metadata'] = json.loads(decrypted) if decrypted else {}
                        except:
                            row['metadata'] = {}
                        del row['metadata_encrypted']
                    else:
                        row['metadata'] = {}
                        
                    files.append(row)
                    
                return files
            except Exception as e:
                logger.error(f"Error getting all files: {e}", exc_info=True)
                return []
                
        return await self.queue.execute(_get_all_files_sync)
        
    async def get_all_reactions(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get all reactions from the database."""
        def _get_all_reactions_sync():
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                
                # Check if the reactions table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reactions'")
                if cursor.fetchone() is None:
                    logger.warning("Reactions table does not exist")
                    return []
                
                cursor.execute("""
                    SELECT r.*, m.author_name as message_author_name 
                    FROM reactions r
                    LEFT JOIN messages m ON r.message_id = m.message_id
                    ORDER BY r.timestamp DESC
                    LIMIT ?
                """, [limit])
                rows = cursor.fetchall()
                
                reactions = []
                for row in dict_factory(cursor, rows):
                    if 'metadata_encrypted' in row and row['metadata_encrypted']:
                        decrypted = decrypt_data(self.encryption_key, row['metadata_encrypted'])
                        try:
                            row['metadata'] = json.loads(decrypted) if decrypted else {}
                        except:
                            row['metadata'] = {}
                        del row['metadata_encrypted']
                    else:
                        row['metadata'] = {}
                        
                    reactions.append(row)
                    
                return reactions
            except Exception as e:
                logger.error(f"Error getting all reactions: {e}", exc_info=True)
                return []
                
        return await self.queue.execute(_get_all_reactions_sync)
        
    async def get_all_message_edits(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get all message edits from the database."""
        def _get_all_message_edits_sync():
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                
                # Check if the message_edits table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='message_edits'")
                if cursor.fetchone() is None:
                    logger.warning("Message edits table does not exist")
                    return []
                
                cursor.execute("""
                    SELECT e.*, m.author_name 
                    FROM message_edits e
                    LEFT JOIN messages m ON e.message_id = m.message_id
                    ORDER BY e.edit_timestamp DESC
                    LIMIT ?
                """, [limit])
                rows = cursor.fetchall()
                
                edits = []
                for row in dict_factory(cursor, rows):
                    # Decrypt content
                    if 'original_content_encrypted' in row and row['original_content_encrypted']:
                        row['original_content'] = decrypt_data(self.encryption_key, row['original_content_encrypted'])
                        del row['original_content_encrypted']
                    
                    if 'new_content_encrypted' in row and row['new_content_encrypted']:
                        row['new_content'] = decrypt_data(self.encryption_key, row['new_content_encrypted'])
                        del row['new_content_encrypted']
                        
                    edits.append(row)
                    
                return edits
            except Exception as e:
                logger.error(f"Error getting all message edits: {e}", exc_info=True)
                return []
                
        return await self.queue.execute(_get_all_message_edits_sync)
        
    async def get_all_channels(self) -> List[Dict[str, Any]]:
        """Get all channels from the database."""
        def _get_all_channels_sync():
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                
                # Check if the channels table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='channels'")
                if cursor.fetchone() is None:
                    logger.warning("Channels table does not exist")
                    return []
                
                cursor.execute("SELECT * FROM channels ORDER BY guild_id, channel_name")
                rows = cursor.fetchall()
                
                return [dict_factory(cursor, [row])[0] for row in rows]
            except Exception as e:
                logger.error(f"Error getting all channels: {e}", exc_info=True)
                return []
                
        return await self.queue.execute(_get_all_channels_sync)

# Helper function to convert SQLite rows to dictionaries
def dict_factory(cursor, rows):
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in rows]

# For backward compatibility
EncryptedDatabase = UnifiedDatabase