import asyncio
from datetime import datetime, timedelta

class UserState:
    """Stores the prompt history and context for a single user."""
    def __init__(self, timeout: int = 3600):
        self.prompt_history = []  # List of (prompt, timestamp) tuples.
        self.timeout = timeout  # Timeout in seconds (default: 1 hour).
        self.clear_task = None

    def add_prompt(self, prompt: str):
        """Add a prompt and reset the auto-clear timer."""
        self._remove_old_prompts()
        self.prompt_history.append((prompt, datetime.now()))
        self.reset_clear_timer()

    def get_context(self) -> str:
        """Return prompt history as a context string."""
        self._remove_old_prompts()
        return "\n".join(prompt for prompt, _ in self.prompt_history)

    def clear_history(self):
        """Clear the prompt history."""
        self.prompt_history = []
        if self.clear_task:
            self.clear_task.cancel()
            self.clear_task = None

    def reset_clear_timer(self):
        if self.clear_task:
            self.clear_task.cancel()
        self.clear_task = asyncio.create_task(self._schedule_clear())

    async def _schedule_clear(self):
        try:
            await asyncio.sleep(self.timeout)
            self.clear_history()
        except asyncio.CancelledError:
            pass

    def _remove_old_prompts(self):
        cutoff = datetime.now() - timedelta(seconds=self.timeout)
        self.prompt_history = [(p, t) for p, t in self.prompt_history if t > cutoff]

class BotState:
    """Manages state for all users."""
    def __init__(self, timeout: int = 3600):
        self.user_states = {}
        self.timeout = timeout

    def get_user_state(self, user_id: str) -> UserState:
        if user_id not in self.user_states:
            self.user_states[user_id] = UserState(timeout=self.timeout)
        return self.user_states[user_id]