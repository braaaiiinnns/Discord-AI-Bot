import asyncio
from datetime import datetime, timedelta
import logging
import time

logger = logging.getLogger('discord_bot')  # Updated logger name for consistency

class UserState:
    """
    Keeps track of a user's state including context, history, and timing.
    """
    
    def __init__(self, user_id: str, timeout: int = 3600):
        """
        Initialize user state.
        
        Args:
            user_id (str): Discord user ID
            timeout (int): Time in seconds before history is cleared
        """
        self.user_id = user_id
        self.timeout = timeout
        self.context = []  # List of prompts and responses
        self.last_access = time.time()
        # Set a maximum context size to prevent memory issues
        self.max_context_items = 20
        
    def add_prompt(self, role: str, content: str):
        """
        Add a prompt to the context.
        
        Args:
            role (str): The role (user or assistant)
            content (str): The prompt content
        """
        # Update last access time
        self.last_access = time.time()
        
        # Add prompt to context
        self.context.append({"role": role, "content": content})
        
        # Limit context size to prevent memory issues
        if len(self.context) > self.max_context_items:
            # Remove oldest messages, but keep at least one system message if present
            system_messages = [i for i in range(len(self.context)) if self.context[i]["role"] == "system"]
            if system_messages and system_messages[0] == 0:
                # Keep the first system message and remove the next oldest message
                self.context.pop(1)
            else:
                # No system message at the start, so just remove the oldest message
                self.context.pop(0)
        
    def get_context(self) -> list:
        """
        Get the current context.
        
        Returns:
            list: List of prompt dictionaries
        """
        # Update last access time
        self.last_access = time.time()
        return self.context
        
    def has_timed_out(self) -> bool:
        """
        Check if the user state has timed out.
        
        Returns:
            bool: True if timed out, False otherwise
        """
        return time.time() - self.last_access > self.timeout
        
    def clear_context(self):
        """Clear the context"""
        self.context = []
        self.last_access = time.time()

class BotState:
    """
    Keeps track of the bot's state, including user states.
    """
    
    def __init__(self, timeout: int = 3600):
        """
        Initialize bot state.
        
        Args:
            timeout (int): Time in seconds before user history is cleared
        """
        self.users = {}  # Dictionary of user states
        self.timeout = timeout
        self.last_cleanup = time.time()
        self.cleanup_interval = 300  # 5 minutes between cleanups
        
    def get_user_state(self, user_id: str) -> UserState:
        """
        Get a user's state.
        
        Args:
            user_id (str): Discord user ID
            
        Returns:
            UserState: The user's state
        """
        # Run periodic cleanup to prevent memory leaks
        if time.time() - self.last_cleanup > self.cleanup_interval:
            self._cleanup()
            
        # Get or create user state
        if user_id not in self.users:
            self.users[user_id] = UserState(user_id, self.timeout)
        return self.users[user_id]
        
    def _cleanup(self):
        """Clean up timed out user states"""
        timed_out_users = []
        for user_id, state in self.users.items():
            if state.has_timed_out():
                timed_out_users.append(user_id)
        
        # Remove timed out users
        for user_id in timed_out_users:
            del self.users[user_id]
            
        # Update last cleanup time
        self.last_cleanup = time.time()
    
    def clear_user_state(self, user_id: str):
        """
        Clear a user's state.
        
        Args:
            user_id (str): Discord user ID
        """
        if user_id in self.users:
            self.users[user_id].clear_context()
            
    def get_user_count(self) -> int:
        """
        Get the number of active users.
        
        Returns:
            int: Number of active users
        """
        return len(self.users)