import os
import logging
import pytz
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Setup logger
logger = logging.getLogger('discord_bot')  # Ensure consistent logger name

# Base directory settings
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DATA_DIRECTORY = os.path.join(PROJECT_ROOT, 'data')

# Timezone for scheduled tasks
TIMEZONE = pytz.timezone('America/Los_Angeles')

# Request limits
REQUEST_LIMIT = 24
IMAGE_REQUEST_LIMIT = 12
RESET_HOURS = 24

# Default limit for summarization
DEFAULT_SUMMARY_LIMIT = 400

# Logging configuration
LOG_DIRECTORY = os.path.join(PROJECT_ROOT, "logs")
LOG_FILE_PATH = os.path.join(LOG_DIRECTORY, "bot.log")
ENABLE_DEBUG_LOGGING = True
LOG_LEVEL = logging.DEBUG

# Message and AI logging configuration
ENABLE_MESSAGE_LOGGING = True  # Enable detailed message logging as required by the dashboard
ENABLE_AI_LOGGING = True  # Keep AI interaction logging for accountability

# API and security keys
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', 'your_default_encryption_key_please_change_in_env')
API_SECRET_KEY = os.getenv('API_SECRET_KEY', 'your_default_api_key_please_change_in_env')