import asyncio
from datetime import datetime, timedelta
import logging

logger = logging.getLogger('discord_bot')  # Updated logger name for consistency

class UserState:
    """Stores the prompt history, context, and request data for a single user."""
    def __init__(self, timeout: int = 3600):
        self.prompt_history = []  # List of (role, content, timestamp) tuples.
        self.timeout = timeout  # Timeout in seconds (default: 1 hour).
        self.clear_task = None
        self.request_data = {}  # Dictionary to store user-specific request data.

    def add_prompt(self, role: str, content: str):
        """Add a prompt or response and reset the auto-clear timer."""
        self._remove_old_prompts()  # Trim old prompts before adding a new one
        self.prompt_history.append((role, content, datetime.now()))
        self.reset_clear_timer()  # Reset the timer to clear history one hour after the last prompt

    def get_context(self) -> list:
        """Return prompt history as a list of dictionaries for conversation context."""
        self._remove_old_prompts()
        return [{"role": role, "content": content} for role, content, _ in self.prompt_history]

    def clear_history(self):
        """Clear the prompt history and request data."""
        self.prompt_history.clear()  # Explicitly clear the list
        self.request_data.clear()  # Explicitly clear the dictionary
        if self.clear_task:
            self.clear_task.cancel()
            self.clear_task = None

    def reset_clear_timer(self):
        """Reset the auto-clear timer for the user's history."""
        if self.clear_task:
            self.clear_task.cancel()  # Cancel any existing clear task
        self.clear_task = asyncio.create_task(self._schedule_clear())  # Schedule a new clear task

    async def _schedule_clear(self):
        """Schedule the clearing of the user's history after the timeout."""
        try:
            await asyncio.sleep(self.timeout)  # Wait for the timeout period
            self.clear_history()  # Clear the user's history
            logger.info("User history cleared after timeout.")  # Log the clearing of history
        except asyncio.CancelledError:
            pass  # Handle task cancellation gracefully

    def _remove_old_prompts(self):
        """Remove prompts that are older than the timeout period."""
        cutoff = datetime.now() - timedelta(seconds=self.timeout)
        self.prompt_history = [
            (role, content, timestamp)
            for role, content, timestamp in self.prompt_history
            if timestamp > cutoff
        ]

class BotState:
    """Manages state for all users."""
    def __init__(self, timeout: int = 3600):
        self.user_states = {}
        self.timeout = timeout
        self.guilds = []  # Initialize as an empty list

    def get_user_state(self, user_id: str) -> UserState:
        if user_id not in self.user_states:
            self.user_states[user_id] = UserState(timeout=self.timeout)
        return self.user_states[user_id]
    
    def get_guilds(self):
        """Return the list of guilds."""
        return self.guilds