import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger('discord_bot')  # Ensure consistent logger name

load_dotenv()

# Discord & API keys.
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
GOOGLE_GENAI_API_KEY = os.getenv('GOOGLE_GENAI_API_KEY')
CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY')
GROK_API_KEY = os.getenv('GROK_API_KEY')

# Request limits.
REQUEST_LIMIT = 24
IMAGE_REQUEST_LIMIT = 12
RESET_HOURS = 24

# Channel and response settings.
DEFAULT_SUMMARY_LIMIT = 250  # Character limit for summaries.
RESPONSE_CHANNEL_ID = os.getenv('RESPONSE_CHANNEL_ID')  

# Role color change settings
DEFAULT_COLOR_ROLES = "Rainbow,Colorful,Vibrant,Spectrum"  # Default list of roles
COLOR_CHANGE_ROLE_NAMES = os.getenv('COLOR_CHANGE_ROLE_NAMES', DEFAULT_COLOR_ROLES).split(',')
COLOR_CHANGE_HOUR = int(os.getenv('COLOR_CHANGE_HOUR', '0'))  # Default hour is midnight (UTC)
COLOR_CHANGE_MINUTE = int(os.getenv('COLOR_CHANGE_MINUTE', '0'))  # Default minute is 0

# File names.
REQUEST_COUNT_FILE = 'user_requests.json'
VECTOR_STORE_ID_FILE = 'vector_store_id.json'
ASSISTANT_IDS_FILE = 'assistant_ids.json'
WARHAMMER_CORE_RULES = '40kCoreRules.txt'

# System-level prompts for each assistant.
GPT_SYSTEM_PROMPT = "You are GPT-4o-mini. Answer in a concise and helpful manner."
GOOGLE_SYSTEM_PROMPT = "You are Google GenAI. Provide factual, accurate, and clear responses."
CLAUDE_SYSTEM_PROMPT = "You are a world-class poet. Respond only with short poems."
GROK_SYSTEM_PROMPT = "You are Grok, an AI assistant from xAI with a sense of humor and intelligence. You provide witty, informative, and creative responses."