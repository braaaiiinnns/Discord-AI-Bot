import os
from config.base import BASE_DATA_DIRECTORY

# Database configuration
DB_DIRECTORY = os.path.join(BASE_DATA_DIRECTORY, 'db')
MESSAGES_DB_PATH = os.path.join(DB_DIRECTORY, 'messages.db')
AI_INTERACTIONS_DB_PATH = os.path.join(DB_DIRECTORY, 'ai_interactions.db')
DB_PATH = os.path.join(DB_DIRECTORY, 'unified.db')
USERS_DB_PATH = os.path.join(DB_DIRECTORY, 'users.db')

# Files directory for attachments/downloads
FILES_DIRECTORY = os.path.join(BASE_DATA_DIRECTORY, 'files')

# Role color and premium role configuration files
ROLE_COLOR_CYCLES_FILE = os.path.join(BASE_DATA_DIRECTORY, 'role_color_cycles.json')
PREMIUM_ROLES_FILE = os.path.join(BASE_DATA_DIRECTORY, 'premium_roles.json')
PREVIOUS_ROLE_COLORS_FILE = os.path.join(BASE_DATA_DIRECTORY, 'previous_role_colors.json')

# Flask session directory
FLASK_SESSION_DIR = os.path.join(BASE_DATA_DIRECTORY, 'flask_session')

# These file references might be unused or could be deprecated
REQUEST_COUNT_FILE = 'user_requests.json'
VECTOR_STORE_ID_FILE = 'vector_store_id.json'
ASSISTANT_IDS_FILE = 'assistant_ids.json'
WARHAMMER_CORE_RULES = '40kCoreRules.txt'