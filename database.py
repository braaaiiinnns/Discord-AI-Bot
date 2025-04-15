import sqlite3
import os
import json
import logging
from datetime import datetime
from ncrypt import encrypt_data, decrypt_data

logger = logging.getLogger('discord_bot')

class EncryptedDatabase:
    """Database handler with encryption support for storing Discord messages and AI interactions."""
    
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
        
        # Ensure the database directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # Initialize connection
        self._connect()
        
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
            
            # Create indexes for faster querying
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_author ON messages (author_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_guild ON messages (guild_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages (channel_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages (timestamp)')
            
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_user ON ai_interactions (user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_guild ON ai_interactions (guild_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_model ON ai_interactions (model)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_timestamp ON ai_interactions (timestamp)')
            
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
    
    def store_message(self, message_data):
        """
        Store a Discord message in the database with encryption for sensitive fields.
        
        Args:
            message_data (dict): Message data containing all required fields
        """
        try:
            # Encrypt sensitive data
            content_encrypted = encrypt_data(self.encryption_key, message_data['content'])
            
            # Encrypt attachments if present
            attachments_encrypted = None
            if message_data.get('attachments'):
                attachments_encrypted = encrypt_data(self.encryption_key, message_data['attachments'])
            
            # Encrypt additional metadata if present
            metadata_encrypted = None
            if message_data.get('metadata'):
                metadata_encrypted = encrypt_data(self.encryption_key, message_data['metadata'])
            
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
                content_encrypted,
                message_data['timestamp'],
                attachments_encrypted,
                message_data['message_type'],
                1 if message_data['is_bot'] else 0,
                metadata_encrypted
            ))
            self.conn.commit()
            logger.debug(f"Stored message {message_data['message_id']} in database")
        except sqlite3.Error as e:
            logger.error(f"Error storing message: {e}")
            self.conn.rollback()
            raise
        except Exception as e:
            logger.error(f"Unexpected error storing message: {e}")
            self.conn.rollback()
            raise
    
    def store_ai_interaction(self, interaction_data):
        """
        Store an AI interaction in the database with encryption for sensitive fields.
        
        Args:
            interaction_data (dict): Interaction data containing all required fields
        """
        try:
            # Encrypt sensitive data
            prompt_encrypted = encrypt_data(self.encryption_key, interaction_data['prompt'])
            response_encrypted = encrypt_data(self.encryption_key, interaction_data['response'])
            
            # Encrypt additional metadata if present
            metadata_encrypted = None
            if interaction_data.get('metadata'):
                metadata_encrypted = encrypt_data(self.encryption_key, interaction_data['metadata'])
            
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
            logger.debug(f"Stored AI interaction {interaction_data['interaction_id']} in database")
        except sqlite3.Error as e:
            logger.error(f"Error storing AI interaction: {e}")
            self.conn.rollback()
            raise
        except Exception as e:
            logger.error(f"Unexpected error storing AI interaction: {e}")
            self.conn.rollback()
            raise
    
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
                        results.append(message_data)
                except Exception as e:
                    logger.error(f"Error decrypting message during search: {e}")
                    continue
                
            return results
        except sqlite3.Error as e:
            logger.error(f"Error searching messages: {e}")
            raise