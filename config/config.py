# Legacy configuration file for backward compatibility
# New code should import directly from config.base, config.ai_config, etc.

# Import all configuration from split files
from config.base import *
from config.ai_config import *
from config.bot_config import *
from config.dashboard_config import *
from config.storage_config import *

# Add a deprecation warning
import warnings
warnings.warn(
    "Direct import from config.config is deprecated. "
    "Please import from the appropriate module: "
    "config.base, config.ai_config, config.bot_config, config.dashboard_config, or config.storage_config",
    DeprecationWarning,
    stacklevel=2
)