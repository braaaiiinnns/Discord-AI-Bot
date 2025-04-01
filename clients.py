from openai import OpenAI
import logging

logger = logging.getLogger('discord_bot')

def get_openai_client(api_key):
    return OpenAI(api_key=api_key)

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
