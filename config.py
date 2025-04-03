import os
from dotenv import load_dotenv

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

# Channel and summary settings.
DEFAULT_SUMMARY_LIMIT = 250  # Character limit for summaries.
SUMMARY_CHANNEL_ID = os.getenv('SUMMARY_CHANNEL_ID')  # Channel ID for posting full responses.

# File names.
REQUEST_COUNT_FILE = 'user_requests.json'
VECTOR_STORE_ID_FILE = 'vector_store_id.json'
ASSISTANT_IDS_FILE = 'assistant_ids.json'
WARHAMMER_CORE_RULES = '40kCoreRules.txt'

# System-level prompts for each assistant.
GPT_SYSTEM_PROMPT = "You are GPT-4o-mini. Answer in a concise and helpful manner."
GOOGLE_SYSTEM_PROMPT = "You are Google GenAI. Provide factual, accurate, and clear responses."
CLAUDE_SYSTEM_PROMPT = "You are a world-class poet. Respond only with short poems."