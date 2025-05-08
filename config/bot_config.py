import os
from config.base import BASE_DATA_DIRECTORY

# Discord Bot Token
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Channel and response settings
RESPONSE_CHANNEL_ID = os.getenv('RESPONSE_CHANNEL_ID')

# Role color change settings
DEFAULT_COLOR_ROLES = "Rainbow,Colorful,Vibrant,Spectrum"
COLOR_CHANGE_ROLE_NAMES = os.getenv('COLOR_CHANGE_ROLE_NAMES', DEFAULT_COLOR_ROLES).split(',')
COLOR_CHANGE_HOUR = int(os.getenv('COLOR_CHANGE_HOUR', '0'))  # Default hour is midnight (UTC)
COLOR_CHANGE_MINUTE = int(os.getenv('COLOR_CHANGE_MINUTE', '0'))  # Default minute is 0

# Premium role settings
DEFAULT_PREMIUM_ROLES = "Premium,Supporter,VIP,Donor"
PREMIUM_ROLE_NAMES = [role.strip() for role in os.getenv('PREMIUM_ROLE_NAMES', DEFAULT_PREMIUM_ROLES).split(',')]

# JSON configuration files
PREMIUM_ROLES_FILE = os.path.join(BASE_DATA_DIRECTORY, 'premium_roles.json')
ROLE_COLOR_CYCLES_FILE = os.path.join(BASE_DATA_DIRECTORY, 'role_color_cycles.json')
PREVIOUS_ROLE_COLORS_FILE = os.path.join(BASE_DATA_DIRECTORY, 'previous_role_colors.json')
MESSAGE_LISTENERS_FILE = os.path.join(BASE_DATA_DIRECTORY, 'message_listeners.json')
ASCII_EMOJI_FILE = os.path.join(BASE_DATA_DIRECTORY, 'static', 'ascii_emoji.json')
TASK_EXAMPLES_FILE = os.path.join(BASE_DATA_DIRECTORY, 'static', 'task_examples.json')
TASKS_FILE = os.path.join(BASE_DATA_DIRECTORY, 'tasks.json')