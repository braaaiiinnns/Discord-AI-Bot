import sqlite3
import os
import json
import logging
import requests
import hashlib
import aiohttp
import asyncio
import threading
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
        self.local_storage = threading.local()  # Thread-local storage for connections
        self.files_dir = os.path.join(os.path.dirname(db_path), "files")
        
        # Ensure the database and files directories exist
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        os.makedirs(self.files_dir, exist_ok=True)
        
        # Initialize connection in the main thread
        self._connect()
        
        # Create database queue for thread-safe operations
        self.queue = DatabaseQueue(max_workers=1)
        
        # Create tables if requested
        if create_tables:
            self._create_tables()
    
    def _connect(self):
        """Establish a connection to the database."""
        try:
            # Store connection in thread-local storage
            if not hasattr(self.local_storage, 'conn'):
                self.local_storage.conn = sqlite3.connect(self.db_path)
                self.local_storage.conn.row_factory = sqlite3.Row  # Return rows as dictionary-like objects
                thread_id = threading.get_ident()
                logger.info(f"Created new database connection for thread {thread_id} at {self.db_path}")
            
            # For the main thread, also store in self.conn for backward compatibility
            if not self.conn:
                self.conn = self.local_storage.conn
            
            return self.local_storage.conn
        except sqlite3.Error as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def _get_connection(self):
        """Get or create a connection for the current thread."""
        if not hasattr(self.local_storage, 'conn'):
            self._connect()
        return self.local_storage.conn
    
    def close(self):
        """Close all database connections."""
        # Close main thread connection if it exists
        if self.conn:
            self.conn.close()
            self.conn = None
        
        # Close thread-local connection if it exists
        if hasattr(self.local_storage, 'conn') and self.local_storage.conn:
            self.local_storage.conn.close()
            delattr(self.local_storage, 'conn')
            
        logger.info("Database connections closed")
        self.queue.stop()
    
    def _create_tables(self):
        """Create necessary tables if they don't exist."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
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
            
            conn.commit()
            logger.info("Database tables created successfully")
        except sqlite3.Error as e:
            logger.error(f"Error creating tables: {e}")
            raise
    
    def store_ai_interaction(self, interaction_data):
        """
        Store an AI interaction in the database.
        
        Args:
            interaction_data (dict): AI interaction data to store
            
        Returns:
            bool: Success status
        """
        # Get thread-local connection at the beginning
        conn = None
        try:
            # Encrypt sensitive data
            prompt_encrypted = encrypt_data(interaction_data['prompt'], self.encryption_key)
            response_encrypted = encrypt_data(interaction_data['response'], self.encryption_key)
            
            # Encrypt metadata if present
            metadata_encrypted = None
            if 'metadata' in interaction_data and interaction_data['metadata']:
                metadata_encrypted = encrypt_data(interaction_data['metadata'], self.encryption_key)
            
            # Get connection for this thread
            conn = self._get_connection()
            thread_id = threading.get_ident()
            logger.debug(f"Using thread {thread_id} connection for AI interaction storage")
            
            # Insert interaction into database
            cursor = conn.cursor()
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
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error storing AI interaction: {e}", exc_info=True)
            try:
                if conn:
                    conn.rollback()
            except Exception as rollback_error:
                logger.error(f"Error during rollback: {rollback_error}")
            return False