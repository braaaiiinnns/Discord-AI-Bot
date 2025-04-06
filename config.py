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

# Request limits.
REQUEST_LIMIT = 24
IMAGE_REQUEST_LIMIT = 12
RESET_HOURS = 24

# Channel and response settings.
DEFAULT_SUMMARY_LIMIT = 250  # Character limit for summaries.
RESPONSE_CHANNEL_ID = os.getenv('SUMMARY_CHANNEL_ID')  # Use channel ID instead of name

# Validate RESPONSE_CHANNEL_ID
if RESPONSE_CHANNEL_ID is None:
    logger.error("RESPONSE_CHANNEL_ID environment variable is not set.")
    raise ValueError("RESPONSE_CHANNEL_ID environment variable is not set.")
try:
    RESPONSE_CHANNEL_ID = int(RESPONSE_CHANNEL_ID)
    logger.info(f"Loaded RESPONSE_CHANNEL_ID: {RESPONSE_CHANNEL_ID}")
except ValueError:
    logger.error("RESPONSE_CHANNEL_ID must be a valid integer.")
    raise ValueError("RESPONSE_CHANNEL_ID must be a valid integer.")

# File names.
REQUEST_COUNT_FILE = 'user_requests.json'
VECTOR_STORE_ID_FILE = 'vector_store_id.json'
ASSISTANT_IDS_FILE = 'assistant_ids.json'
WARHAMMER_CORE_RULES = '40kCoreRules.txt'

# System-level prompts for each assistant.
GPT_SYSTEM_PROMPT = "You are GPT-4o-mini. Answer in a concise and helpful manner."
GOOGLE_SYSTEM_PROMPT = "You are Google GenAI. Provide factual, accurate, and clear responses."
CLAUDE_SYSTEM_PROMPT = "You are a world-class poet. Respond only with short poems."