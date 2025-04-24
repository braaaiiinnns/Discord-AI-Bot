import os
from dotenv import load_dotenv
import logging
import pytz
import tempfile

logger = logging.getLogger('discord_bot')  # Ensure consistent logger name

# Load environment variables from .env file
load_dotenv()

# Bot token and API keys
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
GOOGLE_GENAI_API_KEY = os.getenv('GOOGLE_GENAI_API_KEY')
CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY')
GROK_API_KEY = os.getenv('GROK_API_KEY')

# Request limits
REQUEST_LIMIT = 24
IMAGE_REQUEST_LIMIT = 12
RESET_HOURS = 24

# Default limit for summarization
DEFAULT_SUMMARY_LIMIT = 400

# Channel and response settings
RESPONSE_CHANNEL_ID = os.getenv('RESPONSE_CHANNEL_ID')  

# Role color change settings
DEFAULT_COLOR_ROLES = "Rainbow,Colorful,Vibrant,Spectrum"  # Default list of roles
COLOR_CHANGE_ROLE_NAMES = os.getenv('COLOR_CHANGE_ROLE_NAMES', DEFAULT_COLOR_ROLES).split(',')
COLOR_CHANGE_HOUR = int(os.getenv('COLOR_CHANGE_HOUR', '0'))  # Default hour is midnight (UTC)
COLOR_CHANGE_MINUTE = int(os.getenv('COLOR_CHANGE_MINUTE', '0'))  # Default minute is 0

# Premium role settings
DEFAULT_PREMIUM_ROLES = "Premium,Supporter,VIP,Donor"  # Default list of premium roles
PREMIUM_ROLE_NAMES = [role.strip() for role in os.getenv('PREMIUM_ROLE_NAMES', DEFAULT_PREMIUM_ROLES).split(',')]

# Timezone for scheduled tasks
TIMEZONE = pytz.timezone('America/Los_Angeles')

# Base data directory
BASE_DATA_DIRECTORY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')

# File names
REQUEST_COUNT_FILE = 'user_requests.json'  # Note: This seems unused, consider removing or placing in BASE_DATA_DIRECTORY
VECTOR_STORE_ID_FILE = 'vector_store_id.json'  # Note: This seems unused, consider removing or placing in BASE_DATA_DIRECTORY
ASSISTANT_IDS_FILE = 'assistant_ids.json'  # Note: This seems unused, consider removing or placing in BASE_DATA_DIRECTORY
WARHAMMER_CORE_RULES = '40kCoreRules.txt'  # Note: This seems unused, consider removing or placing in BASE_DATA_DIRECTORY

# JSON file paths (now relative to BASE_DATA_DIRECTORY)
PREMIUM_ROLES_FILE = os.path.join(BASE_DATA_DIRECTORY, 'premium_roles.json')
ROLE_COLOR_CYCLES_FILE = os.path.join(BASE_DATA_DIRECTORY, 'role_color_cycles.json')
PREVIOUS_ROLE_COLORS_FILE = os.path.join(BASE_DATA_DIRECTORY, 'previous_role_colors.json')
MESSAGE_LISTENERS_FILE = os.path.join(BASE_DATA_DIRECTORY, 'message_listeners.json')
ASCII_EMOJI_FILE = os.path.join(BASE_DATA_DIRECTORY, 'static', 'ascii_emoji.json')
TASK_EXAMPLES_FILE = os.path.join(BASE_DATA_DIRECTORY, 'static', 'task_examples.json')
TASKS_FILE = os.path.join(BASE_DATA_DIRECTORY, 'tasks.json')

# System prompts
GPT_SYSTEM_PROMPT = "You are a helpful, friendly AI assistant. Provide accurate and concise information."
GOOGLE_SYSTEM_PROMPT = "You are Google's Gemini AI model, designed to be helpful, accurate, and informative. Provide comprehensive and detailed answers to questions, offering examples and explanations where appropriate. Your responses should be thorough and well-structured."
CLAUDE_SYSTEM_PROMPT = "You are Claude, an AI assistant created by Anthropic. Respond to queries with the eloquence and creativity of a poet while remaining helpful and accurate."
GROK_SYSTEM_PROMPT = "You are Grok, an AI made by xAI. You have a humorous and witty personality. Provide answers that are accurate but with a touch of humor."

# Database configuration
DB_DIRECTORY = os.path.join(BASE_DATA_DIRECTORY, 'db')  # Correct DB directory
MESSAGES_DB_PATH = os.path.join(DB_DIRECTORY, 'messages.db')
AI_INTERACTIONS_DB_PATH = os.path.join(DB_DIRECTORY, 'ai_interactions.db')
# Unified database path (this will be the default after migration)
DB_PATH = os.path.join(DB_DIRECTORY, 'unified.db')

# Files directory for attachments/downloads
FILES_DIRECTORY = os.path.join(BASE_DATA_DIRECTORY, 'files')  # Correct files directory

# Encryption key for securing database content
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', 'your_default_encryption_key_please_change_in_env')

# API Key for securing API endpoints
API_SECRET_KEY = os.getenv('API_SECRET_KEY', 'your_default_api_key_please_change_in_env')

# Logging configuration
LOG_DIRECTORY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
LOG_FILE_PATH = os.path.join(LOG_DIRECTORY, "bot.log")  # Define the full log file path
ENABLE_DEBUG_LOGGING = True  # Force debug logging ON
LOG_LEVEL = logging.DEBUG  # Set log level to DEBUG

# Message and AI logging configuration
ENABLE_MESSAGE_LOGGING = True  # Enable detailed message logging as required by the dashboard
ENABLE_AI_LOGGING = True  # Keep AI interaction logging for accountability

# API configuration
API_HOST = os.getenv('API_HOST', '127.0.0.1')
API_PORT = int(os.getenv('API_PORT', '5000'))

# Dashboard configuration
ENABLE_DASHBOARD = True
DASHBOARD_HOST = os.getenv('DASHBOARD_HOST', '127.0.0.1')
DASHBOARD_PORT = int(os.getenv('DASHBOARD_PORT', '8050'))  # Changed from 8050 to 8080 to avoid conflicts
FLASK_SESSION_DIR = os.path.join(BASE_DATA_DIRECTORY, 'flask_session')  # Correct Flask session directory

# Define the directory for session files if not already set
FLASK_SESSION_DIR = os.environ.get('FLASK_SESSION_DIR', os.path.join(tempfile.gettempdir(), 'discord_bot_sessions'))

# Discord OAuth for Dashboard
DISCORD_CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
DISCORD_REDIRECT_URI = os.getenv('DISCORD_REDIRECT_URI', f'http://{DASHBOARD_HOST}:{DASHBOARD_PORT}/callback')
DASHBOARD_REQUIRE_LOGIN = os.getenv('DASHBOARD_REQUIRE_LOGIN', 'true').lower() == 'true'