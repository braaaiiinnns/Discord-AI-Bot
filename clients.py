import openai
import logging

logger = logging.getLogger('discord_bot')

def get_openai_client(api_key):
    # For older versions of openai library (< 1.0.0)
    openai.api_key = api_key
    return openai

def get_google_genai_client(api_key):
    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except ImportError as e:
        logger.error("Google GenAI library not installed. Please install google-genai.")
        return None

def get_claude_client(api_key):
    try:
        import anthropic
        return anthropic.Client(api_key=api_key)
    except ImportError as e:
        logger.error("Anthropic API library not installed. Please install anthropic.")
        return None

def get_grok_client(api_key):
    try:
        # For older versions of openai library (< 1.0.0)
        # Set the API key and base URL
        import openai
        openai.api_key = api_key
        openai.api_base = "https://api.x.ai/v1"
        return openai
    except ImportError as e:
        logger.error("OpenAI library not installed. Please install openai.")
        return None
