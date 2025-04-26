"""
User model for Discord OAuth2 authentication.
Handles user data, sessions, and API key management.
"""

import asyncio
import json
import os
import secrets
import sqlite3
import time
import uuid
from typing import Dict, List, Optional, Any, Tuple

from utils.database import get_db_path
from utils.logger import setup_logger

logger = setup_logger('discord_bot.api.user_model')

# Database file path
USER_DB_PATH = get_db_path('users.db')

class UserManager:
    def __init__(self, db_path: str = USER_DB_PATH):
        self.db_path = db_path
        self._initialize_db()

    def _initialize_db(self) -> None:
        """Initialize the user database schema."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Create users table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                discriminator TEXT,
                email TEXT,
                avatar TEXT,
                api_key TEXT UNIQUE,
                is_admin INTEGER DEFAULT 0,
                access_status TEXT DEFAULT 'pending',
                created_at INTEGER,
                updated_at INTEGER,
                last_login INTEGER,
                access_token TEXT,
                refresh_token TEXT,
                token_expires_at INTEGER
            )
            ''')

            # Create sessions table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at INTEGER,
                expires_at INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            ''')

            # Create access requests table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS access_requests (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                message TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            ''')

            conn.commit()
            
            # Add access_status column to users table if it doesn't exist
            try:
                cursor.execute('SELECT access_status FROM users LIMIT 1')
            except sqlite3.OperationalError:
                cursor.execute('ALTER TABLE users ADD COLUMN access_status TEXT DEFAULT "pending"')
                conn.commit()
                
            # Add last_login column to users table if it doesn't exist
            try:
                cursor.execute('SELECT last_login FROM users LIMIT 1')
            except sqlite3.OperationalError:
                cursor.execute('ALTER TABLE users ADD COLUMN last_login INTEGER')
                logger.info("Added last_login column to users table")
                conn.commit()
                
            conn.close()
        except Exception as e:
            logger.error(f"Error initializing user database: {e}", exc_info=True)

    async def create_or_update_user(self, user_data: Dict[str, Any], token_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create or update a user record from Discord OAuth data.
        
        Args:
            user_data: User information from Discord API
            token_data: OAuth token data from Discord API
            
        Returns:
            Dict containing the user record
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Extract user data from Discord response
            user_id = user_data.get('id')
            username = user_data.get('username')
            discriminator = user_data.get('discriminator', '')
            email = user_data.get('email')
            avatar = user_data.get('avatar')
            
            # Extract token data
            access_token = token_data.get('access_token')
            refresh_token = token_data.get('refresh_token')
            expires_in = token_data.get('expires_in', 0)
            token_expires_at = int(time.time()) + expires_in
            
            # Check if user exists
            cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            existing_user = cursor.fetchone()
            
            current_time = int(time.time())
            
            if existing_user:
                # Update existing user
                cursor.execute('''
                UPDATE users SET 
                    username = ?, 
                    discriminator = ?, 
                    email = ?, 
                    avatar = ?, 
                    updated_at = ?,
                    access_token = ?,
                    refresh_token = ?,
                    token_expires_at = ?
                WHERE id = ?
                ''', (
                    username, 
                    discriminator, 
                    email, 
                    avatar, 
                    current_time,
                    access_token,
                    refresh_token,
                    token_expires_at,
                    user_id
                ))
                
                # Fetch the updated user
                cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
                user_record = cursor.fetchone()
            else:
                # Create new user with a generated API key
                api_key = secrets.token_urlsafe(32)
                
                cursor.execute('''
                INSERT INTO users (
                    id, username, discriminator, email, avatar, api_key,
                    is_admin, created_at, updated_at, access_token, refresh_token, token_expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_id, username, discriminator, email, avatar, api_key,
                    0, current_time, current_time, access_token, refresh_token, token_expires_at
                ))
                
                # Fetch the new user
                cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
                user_record = cursor.fetchone()
            
            conn.commit()
            
            # Convert the tuple to a dict
            user_dict = {
                'id': user_record[0],
                'username': user_record[1],
                'discriminator': user_record[2],
                'email': user_record[3],
                'avatar': user_record[4],
                'api_key': user_record[5],
                'is_admin': bool(user_record[6]),
                'created_at': user_record[7],
                'updated_at': user_record[8],
                'access_token': user_record[9],
                'refresh_token': user_record[10],
                'token_expires_at': user_record[11]
            }
            
            conn.close()
            return user_dict
            
        except Exception as e:
            logger.error(f"Error creating/updating user: {e}", exc_info=True)
            if 'conn' in locals():
                conn.close()
            raise

    async def create_session(self, session_id: str, user_id: str, expires_at: str = None) -> Dict[str, Any]:
        """
        Create a new session for a user.
        
        Args:
            session_id: Session ID to create
            user_id: Discord user ID
            expires_at: Session expiry time (ISO format string or None)
            
        Returns:
            Dictionary with session data if successful, None if failed
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            current_time = int(time.time())
            
            # If expires_at is provided as ISO string, convert to timestamp
            if expires_at:
                try:
                    # Parse ISO format datetime string to timestamp
                    from datetime import datetime
                    dt = datetime.fromisoformat(expires_at)
                    expires_at_ts = int(dt.timestamp())
                except Exception as e:
                    logger.error(f"Error parsing expires_at: {e}", exc_info=True)
                    expires_at_ts = current_time + (30 * 24 * 60 * 60)  # Default to 30 days
            else:
                expires_at_ts = current_time + (30 * 24 * 60 * 60)  # 30 days
            
            # Create the session
            cursor.execute('''
            INSERT INTO sessions (id, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            ''', (session_id, user_id, current_time, expires_at_ts))
            
            conn.commit()
            
            # Return session data
            session_data = {
                'id': session_id,
                'user_id': user_id,
                'created_at': current_time,
                'expires_at': expires_at_ts
            }
            
            conn.close()
            return session_data
            
        except Exception as e:
            logger.error(f"Error creating session: {e}", exc_info=True)
            if 'conn' in locals():
                conn.close()
            return None

    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.
        
        Args:
            session_id: Session ID to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
            deleted = cursor.rowcount > 0
            
            conn.commit()
            conn.close()
            
            return deleted
            
        except Exception as e:
            logger.error(f"Error deleting session: {e}", exc_info=True)
            if 'conn' in locals():
                conn.close()
            return False

    async def get_user_by_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a user by their session ID.
        
        Args:
            session_id: Session ID
            
        Returns:
            User dict if found and session is valid, None otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            current_time = int(time.time())
            
            # Get the session and check if it's expired
            cursor.execute('''
            SELECT s.user_id, s.expires_at, u.*
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.id = ? AND s.expires_at > ?
            ''', (session_id, current_time))
            
            result = cursor.fetchone()
            conn.close()
            
            if not result:
                return None
                
            # Result format is (user_id, expires_at, *user_fields)
            user_dict = {
                'id': result[2],  # user id
                'username': result[3],
                'discriminator': result[4],
                'email': result[5],
                'avatar': result[6],
                'api_key': result[7],
                'is_admin': bool(result[8]),
                'created_at': result[9],
                'updated_at': result[10],
                'access_token': result[11],
                'refresh_token': result[12],
                'token_expires_at': result[13]
            }
            
            return user_dict
            
        except Exception as e:
            logger.error(f"Error getting user by session: {e}", exc_info=True)
            if 'conn' in locals():
                conn.close()
            return None

    async def get_user_by_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """
        Get a user by their API key.
        
        Args:
            api_key: User API key
            
        Returns:
            User dict if found, None otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM users WHERE api_key = ?', (api_key,))
            user_record = cursor.fetchone()
            conn.close()
            
            if not user_record:
                return None
                
            user_dict = {
                'id': user_record[0],
                'username': user_record[1],
                'discriminator': user_record[2],
                'email': user_record[3],
                'avatar': user_record[4],
                'api_key': user_record[5],
                'is_admin': bool(user_record[6]),
                'created_at': user_record[7],
                'updated_at': user_record[8],
                'access_token': user_record[9],
                'refresh_token': user_record[10],
                'token_expires_at': user_record[11]
            }
            
            return user_dict
            
        except Exception as e:
            logger.error(f"Error getting user by API key: {e}", exc_info=True)
            if 'conn' in locals():
                conn.close()
            return None

    async def get_user_by_discord_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a user by their Discord user ID.
        
        Args:
            user_id: Discord user ID
            
        Returns:
            User dict if found, None otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            user_record = cursor.fetchone()
            conn.close()
            
            if not user_record:
                return None
                
            user_dict = {
                'id': user_record[0],
                'username': user_record[1],
                'discriminator': user_record[2],
                'email': user_record[3],
                'avatar': user_record[4],
                'api_key': user_record[5],
                'is_admin': bool(user_record[6]),
                'access_status': user_record[7] if len(user_record) > 7 else 'pending',
                'created_at': user_record[8] if len(user_record) > 8 else None,
                'updated_at': user_record[9] if len(user_record) > 9 else None,
                'access_token': user_record[10] if len(user_record) > 10 else None,
                'refresh_token': user_record[11] if len(user_record) > 11 else None,
                'token_expires_at': user_record[12] if len(user_record) > 12 else None
            }
            
            return user_dict
            
        except Exception as e:
            logger.error(f"Error getting user by Discord ID: {e}", exc_info=True)
            if 'conn' in locals():
                conn.close()
            return None

    async def update_user(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update a user's information in the database.
        
        Args:
            user_id: Discord user ID
            updates: Dictionary of fields to update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Build the SQL query dynamically based on what fields are being updated
            update_fields = []
            values = []
            
            for field, value in updates.items():
                # Skip any fields that aren't database columns
                if field not in ['username', 'discriminator', 'email', 'avatar', 
                                'api_key', 'is_admin', 'access_status', 
                                'access_token', 'refresh_token', 'token_expires_at', 
                                'updated_at', 'last_login']:
                    continue
                    
                update_fields.append(f"{field} = ?")
                values.append(value)
            
            # Always update the updated_at timestamp
            if 'updated_at' not in updates:
                update_fields.append("updated_at = ?")
                values.append(int(time.time()))
                
            # Only proceed if there are fields to update
            if not update_fields:
                logger.warning(f"No valid fields to update for user {user_id}")
                conn.close()
                return False
                
            # Construct and execute the SQL query
            sql = f"UPDATE users SET {', '.join(update_fields)} WHERE id = ?"
            values.append(user_id)
            
            cursor.execute(sql, values)
            updated = cursor.rowcount > 0
            
            conn.commit()
            conn.close()
            
            return updated
            
        except Exception as e:
            logger.error(f"Error updating user {user_id}: {e}", exc_info=True)
            if 'conn' in locals():
                conn.close()
            return False

    async def create_user(self, user_data: Dict[str, Any]) -> bool:
        """
        Create a new user in the database.
        
        Args:
            user_data: Dictionary containing user information
            
        Returns:
            True if successful, False otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Required fields
            user_id = user_data.get('id')
            username = user_data.get('username')
            
            if not user_id or not username:
                logger.error("Missing required fields (id, username) for user creation")
                conn.close()
                return False
                
            # Optional fields with defaults
            discriminator = user_data.get('discriminator', '0')
            email = user_data.get('email')
            avatar = user_data.get('avatar')
            api_key = user_data.get('api_key', secrets.token_urlsafe(32))
            is_admin = 1 if user_data.get('is_admin', False) else 0
            access_status = user_data.get('access_status', 'pending')
            
            current_time = int(time.time())
            created_at = user_data.get('created_at', current_time)
            updated_at = user_data.get('updated_at', current_time)
            
            # OAuth2 tokens if available
            access_token = user_data.get('access_token')
            refresh_token = user_data.get('refresh_token')
            token_expires_at = user_data.get('token_expires_at')
            
            # Create the user
            cursor.execute('''
            INSERT INTO users (
                id, username, discriminator, email, avatar, api_key,
                is_admin, access_status, created_at, updated_at,
                access_token, refresh_token, token_expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id, username, discriminator, email, avatar, api_key,
                is_admin, access_status, created_at, updated_at,
                access_token, refresh_token, token_expires_at
            ))
            
            conn.commit()
            conn.close()
            
            return True
            
        except Exception as e:
            logger.error(f"Error creating user: {e}", exc_info=True)
            if 'conn' in locals():
                conn.close()
            return False

    async def update_user_api_key(self, user_id: str, api_key: str) -> bool:
        """
        Update a user's API key.
        
        Args:
            user_id: User ID
            api_key: New API key
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Log the operation (without exposing the full key)
            key_preview = api_key[:5] + "..." if api_key and len(api_key) > 8 else "[invalid key]"
            logger.info(f"Updating API key for user {user_id}: {key_preview}")
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('UPDATE users SET api_key = ? WHERE id = ?', (api_key, user_id))
            updated = cursor.rowcount > 0
            
            conn.commit()
            conn.close()
            
            return updated
            
        except Exception as e:
            logger.error(f"Error updating user API key: {e}", exc_info=True)
            if 'conn' in locals():
                conn.close()
            return False

    async def set_user_admin(self, user_id: str, is_admin: bool = True) -> bool:
        """
        Set a user's admin status.
        
        Args:
            user_id: User ID
            is_admin: Admin status (True/False)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('UPDATE users SET is_admin = ? WHERE id = ?', (1 if is_admin else 0, user_id))
            updated = cursor.rowcount > 0
            
            conn.commit()
            conn.close()
            
            return updated
            
        except Exception as e:
            logger.error(f"Error setting user admin status: {e}", exc_info=True)
            if 'conn' in locals():
                conn.close()
            return False

    async def get_all_users(self) -> List[Dict[str, Any]]:
        """
        Get all users.
        
        Returns:
            List of user dicts
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM users ORDER BY username')
            users = cursor.fetchall()
            
            user_list = []
            for user in users:
                user_dict = dict(user)
                user_dict['is_admin'] = bool(user_dict['is_admin'])
                user_list.append(user_dict)
                
            conn.close()
            return user_list
            
        except Exception as e:
            logger.error(f"Error getting all users: {e}", exc_info=True)
            if 'conn' in locals():
                conn.close()
            return []

    async def clean_expired_sessions(self) -> int:
        """
        Delete all expired sessions.
        
        Returns:
            Number of deleted sessions
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            current_time = int(time.time())
            
            cursor.execute('DELETE FROM sessions WHERE expires_at < ?', (current_time,))
            deleted_count = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning expired sessions: {e}", exc_info=True)
            if 'conn' in locals():
                conn.close()
            return 0

    async def request_dashboard_access(self, user_id: str, message: str = "") -> Optional[str]:
        """
        Create a new access request for a user.
        
        Args:
            user_id: Discord user ID
            message: Optional message from the user
            
        Returns:
            Request ID if successful, None otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if user has an existing pending request
            cursor.execute('SELECT id FROM access_requests WHERE user_id = ? AND status = "pending"', (user_id,))
            existing = cursor.fetchone()
            
            if existing:
                return existing[0]  # Return the existing request ID
            
            # Generate a new request ID
            request_id = str(uuid.uuid4())
            current_time = int(time.time())
            
            # Create the request
            cursor.execute('''
            INSERT INTO access_requests (id, user_id, status, message, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (request_id, user_id, 'pending', message, current_time, current_time))
            
            # Update user's access_status
            cursor.execute('UPDATE users SET access_status = "requested" WHERE id = ?', (user_id,))
            
            conn.commit()
            conn.close()
            
            return request_id
            
        except Exception as e:
            logger.error(f"Error creating access request: {e}", exc_info=True)
            if 'conn' in locals():
                conn.close()
            return None

    async def approve_access_request(self, request_id: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Approve a dashboard access request.
        
        Args:
            request_id: Request ID to approve
            
        Returns:
            Tuple of (success, user_data)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            current_time = int(time.time())
            
            # Get the request and associated user
            cursor.execute('''
            SELECT ar.user_id, u.*
            FROM access_requests ar
            JOIN users u ON ar.user_id = u.id
            WHERE ar.id = ? AND ar.status = "pending"
            ''', (request_id,))
            
            result = cursor.fetchone()
            
            if not result:
                conn.close()
                return False, None
                
            user_id = result[0]
            
            # Update the request status
            cursor.execute('''
            UPDATE access_requests 
            SET status = "approved", updated_at = ?
            WHERE id = ?
            ''', (current_time, request_id))
            
            # Update user status
            cursor.execute('''
            UPDATE users
            SET access_status = "approved", updated_at = ?
            WHERE id = ?
            ''', (current_time, user_id))
            
            conn.commit()
            
            # Get updated user data
            cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            user_record = cursor.fetchone()
            
            if not user_record:
                conn.close()
                return True, None
                
            user_dict = {
                'id': user_record[0],
                'username': user_record[1],
                'discriminator': user_record[2],
                'email': user_record[3],
                'avatar': user_record[4],
                'api_key': user_record[5],
                'is_admin': bool(user_record[6]),
                'access_status': user_record[7],
                'created_at': user_record[8],
                'updated_at': user_record[9],
                'access_token': user_record[10],
                'refresh_token': user_record[11],
                'token_expires_at': user_record[12]
            }
            
            conn.close()
            return True, user_dict
            
        except Exception as e:
            logger.error(f"Error approving access request: {e}", exc_info=True)
            if 'conn' in locals():
                conn.close()
            return False, None

    async def deny_access_request(self, request_id: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Deny a dashboard access request.
        
        Args:
            request_id: Request ID to deny
            
        Returns:
            Tuple of (success, user_data)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            current_time = int(time.time())
            
            # Get the request and associated user
            cursor.execute('''
            SELECT ar.user_id, u.*
            FROM access_requests ar
            JOIN users u ON ar.user_id = u.id
            WHERE ar.id = ? AND ar.status = "pending"
            ''', (request_id,))
            
            result = cursor.fetchone()
            
            if not result:
                conn.close()
                return False, None
                
            user_id = result[0]
            
            # Update the request status
            cursor.execute('''
            UPDATE access_requests 
            SET status = "denied", updated_at = ?
            WHERE id = ?
            ''', (current_time, request_id))
            
            # Update user status
            cursor.execute('''
            UPDATE users
            SET access_status = "denied", updated_at = ?
            WHERE id = ?
            ''', (current_time, user_id))
            
            conn.commit()
            
            # Get updated user data
            cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            user_record = cursor.fetchone()
            
            if not user_record:
                conn.close()
                return True, None
                
            user_dict = {
                'id': user_record[0],
                'username': user_record[1],
                'discriminator': user_record[2],
                'email': user_record[3],
                'avatar': user_record[4],
                'api_key': user_record[5],
                'is_admin': bool(user_record[6]),
                'access_status': user_record[7],
                'created_at': user_record[8],
                'updated_at': user_record[9],
                'access_token': user_record[10],
                'refresh_token': user_record[11],
                'token_expires_at': user_record[12]
            }
            
            conn.close()
            return True, user_dict
            
        except Exception as e:
            logger.error(f"Error denying access request: {e}", exc_info=True)
            if 'conn' in locals():
                conn.close()
            return False, None

    async def get_pending_access_requests(self) -> List[Dict[str, Any]]:
        """
        Get all pending access requests.
        
        Returns:
            List of access request dicts with user info
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT ar.*, u.username, u.discriminator, u.avatar, u.email, u.is_admin
            FROM access_requests ar
            JOIN users u ON ar.user_id = u.id
            WHERE ar.status = "pending"
            ORDER BY ar.created_at DESC
            ''')
            
            requests = cursor.fetchall()
            
            request_list = []
            for req in requests:
                req_dict = dict(req)
                req_dict['is_admin'] = bool(req_dict['is_admin'])
                request_list.append(req_dict)
                
            conn.close()
            return request_list
            
        except Exception as e:
            logger.error(f"Error getting pending access requests: {e}", exc_info=True)
            if 'conn' in locals():
                conn.close()
            return []
    
    async def update_user_access_status(self, user_id: str, status: str) -> bool:
        """
        Update a user's access status directly.
        
        Args:
            user_id: User ID
            status: New access status ('pending', 'requested', 'approved', 'denied')
            
        Returns:
            True if successful, False otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            current_time = int(time.time())
            
            cursor.execute('''
            UPDATE users
            SET access_status = ?, updated_at = ?
            WHERE id = ?
            ''', (status, current_time, user_id))
            
            updated = cursor.rowcount > 0
            conn.commit()
            conn.close()
            
            return updated
            
        except Exception as e:
            logger.error(f"Error updating user access status: {e}", exc_info=True)
            if 'conn' in locals():
                conn.close()
            return False

# Create a singleton instance of UserManager
user_manager = UserManager()