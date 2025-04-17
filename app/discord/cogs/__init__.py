# Discord.py cogs for organizing commands
"""
Cogs package for organizing Discord.py commands into modular components.

Cogs allow you to organize bot commands, listeners, and state into separate classes.
Each cog should focus on a specific functionality or category of commands.
"""

# Import cogs here to make them available via the package
from .ai_commands import AICogCommands
from .utility_commands import UtilityCogCommands
from .role_color_cog import RoleColorCog
