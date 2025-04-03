import asyncio
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class UserState:
    """Stores the prompt history, context, and request data for a single user."""
    def __init__(self, timeout: int = 3600):
        self.prompt_history = []  # List of (role, content, timestamp) tuples.
        self.timeout = timeout  # Timeout in seconds (default: 1 hour).
        self.clear_task = None
        self.request_data = {}  # Dictionary to store user-specific request data.

    def add_prompt(self, role: str, content: str):
        """Add a prompt or response and reset the auto-clear timer."""
        self._remove_old_prompts()
        self.prompt_history.append((role, content, datetime.now()))
        self.reset_clear_timer()

    def get_context(self) -> list:
        """Return prompt history as a list of dictionaries for conversation context."""
        self._remove_old_prompts()
        return [{"role": role, "content": content} for role, content, _ in self.prompt_history]

    def clear_history(self):
        """Clear the prompt history and request data."""
        logger.info("Clearing history for user.")
        self.prompt_history.clear()  # Explicitly clear the list
        self.request_data.clear()  # Explicitly clear the dictionary
        if self.clear_task:
            self.clear_task.cancel()
            self.clear_task = None
        logger.info("History cleared successfully.")

    def reset_clear_timer(self):
        """Reset the auto-clear timer for the user's history."""
        if self.clear_task:
            self.clear_task.cancel()
        self.clear_task = asyncio.create_task(self._schedule_clear())

    async def _schedule_clear(self):
        """Schedule the clearing of the user's history after the timeout."""
        try:
            await asyncio.sleep(self.timeout)
            self.clear_history()
        except asyncio.CancelledError:
            pass

    def _remove_old_prompts(self):
        """Remove prompts that are older than the timeout period."""
        cutoff = datetime.now() - timedelta(seconds=self.timeout)
        self.prompt_history = [(role, content, timestamp) for role, content, timestamp in self.prompt_history if timestamp > cutoff]

class BotState:
    """Manages state for all users."""
    def __init__(self, timeout: int = 3600):
        self.user_states = {}
        self.timeout = timeout

    def get_user_state(self, user_id: str) -> UserState:
        if user_id not in self.user_states:
            self.user_states[user_id] = UserState(timeout=self.timeout)
        return self.user_states[user_id]