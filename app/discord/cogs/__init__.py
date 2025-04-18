# Discord.py cogs for organizing commands
"""
Cogs package for organizing Discord.py commands into modular components.

Cogs allow you to organize bot commands, listeners, and state into separate classes.
Each cog should focus on a specific functionality or category of commands.
"""

# Import cogs here to make them available via the package
from .gen_ai_cog import AICogCommands
from .role_color_cog import RoleColorCog
from .message_listeners_cog import MessageListenersCog
from .premium_cog import PremiumRolesCog
from .user_state_cog import UserStateCog
from .images_cog import ImageGeneration
from .dashboard_cog import Dashboard
