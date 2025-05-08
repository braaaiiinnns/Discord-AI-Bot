"""
Configuration package initialization.
This allows importing configuration directly from the config package.
"""

# Import settings from all configuration modules
from config.base import *
from config.ai_config import *
from config.bot_config import *
from config.dashboard_config import *
from config.storage_config import *

# Add version information
__version__ = '1.0.0'