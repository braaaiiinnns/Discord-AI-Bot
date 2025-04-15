import os
from dotenv import load_dotenv
import logging
import pytz

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
DEFAULT_SUMMARY_LIMIT = 1500

# Channel and response settings
RESPONSE_CHANNEL_ID = os.getenv('RESPONSE_CHANNEL_ID')  

# Role color change settings
DEFAULT_COLOR_ROLES = "Rainbow,Colorful,Vibrant,Spectrum"  # Default list of roles
COLOR_CHANGE_ROLE_NAMES = os.getenv('COLOR_CHANGE_ROLE_NAMES', DEFAULT_COLOR_ROLES).split(',')
COLOR_CHANGE_HOUR = int(os.getenv('COLOR_CHANGE_HOUR', '0'))  # Default hour is midnight (UTC)
COLOR_CHANGE_MINUTE = int(os.getenv('COLOR_CHANGE_MINUTE', '0'))  # Default minute is 0

# Timezone for scheduled tasks
TIMEZONE = pytz.timezone('America/Los_Angeles')

# File names
REQUEST_COUNT_FILE = 'user_requests.json'
VECTOR_STORE_ID_FILE = 'vector_store_id.json'
ASSISTANT_IDS_FILE = 'assistant_ids.json'
WARHAMMER_CORE_RULES = '40kCoreRules.txt'

# System prompts
GPT_SYSTEM_PROMPT = "You are a helpful, friendly AI assistant. Provide accurate and concise information."
GOOGLE_SYSTEM_PROMPT = "You are Google's Gemini AI model, designed to be helpful, accurate, and informative. Answer questions concisely and clearly."
CLAUDE_SYSTEM_PROMPT = "You are Claude, an AI assistant created by Anthropic. Respond to queries with the eloquence and creativity of a poet while remaining helpful and accurate."
GROK_SYSTEM_PROMPT = "You are Grok, an AI made by xAI. You have a humorous and witty personality. Provide answers that are accurate but with a touch of humor."

# Database configuration
DB_DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
MESSAGES_DB_PATH = os.path.join(DB_DIRECTORY, 'messages.db')
AI_INTERACTIONS_DB_PATH = os.path.join(DB_DIRECTORY, 'ai_interactions.db')

# Encryption key for securing database content
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', 'your_default_encryption_key_please_change_in_env')

# Message and AI logging configuration
ENABLE_MESSAGE_LOGGING = True
ENABLE_AI_LOGGING = True

# Dashboard configuration
ENABLE_DASHBOARD = True
DASHBOARD_HOST = os.getenv('DASHBOARD_HOST', '127.0.0.1')
DASHBOARD_PORT = int(os.getenv('DASHBOARD_PORT', '8050'))

# Discord OAuth for Dashboard
DISCORD_CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
DISCORD_REDIRECT_URI = os.getenv('DISCORD_REDIRECT_URI', f'http://{DASHBOARD_HOST}:{DASHBOARD_PORT}/callback')
DASHBOARD_REQUIRE_LOGIN = os.getenv('DASHBOARD_REQUIRE_LOGIN', 'true').lower() == 'true'