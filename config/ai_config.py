import os
from config.base import logger

# AI API keys
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
GOOGLE_GENAI_API_KEY = os.getenv('GOOGLE_GENAI_API_KEY')
CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY')
GROK_API_KEY = os.getenv('GROK_API_KEY')

# AI Model Configuration
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
GOOGLE_GENAI_MODEL = os.getenv('GOOGLE_GENAI_MODEL', 'gemini-1.5-pro')
CLAUDE_MODEL = os.getenv('CLAUDE_MODEL', 'claude-3-5-haiku-20241022')
GROK_MODEL = os.getenv('GROK_MODEL', 'grok-3-beta')

# Summarization model configuration
# Default to Google's model for backward compatibility
SUMMARIZATION_MODEL = os.getenv('SUMMARIZATION_MODEL', GOOGLE_GENAI_MODEL)
SUMMARIZATION_PROVIDER = os.getenv('SUMMARIZATION_PROVIDER', 'google')  # Options: google, openai, claude, grok

# System prompts
GPT_SYSTEM_PROMPT = "You are a helpful, friendly AI assistant. Provide accurate and concise information."
GOOGLE_SYSTEM_PROMPT = "You are Google's Gemini AI model, designed to be helpful, accurate, and informative. Provide comprehensive and detailed answers to questions, offering examples and explanations where appropriate. Your responses should be thorough and well-structured."
CLAUDE_SYSTEM_PROMPT = "You are Claude, an AI assistant created by Anthropic. Respond to queries with the eloquence and creativity of a poet while remaining helpful and accurate."
GROK_SYSTEM_PROMPT = "You are Grok, an AI made by xAI. You have a humorous and witty personality. Provide answers that are accurate but with a touch of humor."

# AI Provider Configuration Classes
class OpenAIConfig:
    MODEL = OPENAI_MODEL
    TEMPERATURE = float(os.getenv('OPENAI_TEMPERATURE', '0.7'))
    MAX_TOKENS = int(os.getenv('OPENAI_MAX_TOKENS', '4096'))
    TOP_P = float(os.getenv('OPENAI_TOP_P', '1.0'))
    FREQUENCY_PENALTY = float(os.getenv('OPENAI_FREQUENCY_PENALTY', '0.0'))
    PRESENCE_PENALTY = float(os.getenv('OPENAI_PRESENCE_PENALTY', '0.0'))
    TIMEOUT = int(os.getenv('OPENAI_TIMEOUT', '60'))  # Seconds

class GoogleConfig:
    MODEL = GOOGLE_GENAI_MODEL
    TEMPERATURE = float(os.getenv('GOOGLE_TEMPERATURE', '0.8'))
    MAX_OUTPUT_TOKENS = int(os.getenv('GOOGLE_MAX_OUTPUT_TOKENS', '4096'))
    TOP_P = float(os.getenv('GOOGLE_TOP_P', '0.95'))
    TOP_K = int(os.getenv('GOOGLE_TOP_K', '64'))
    
class ClaudeConfig:
    MODEL = CLAUDE_MODEL
    TEMPERATURE = float(os.getenv('CLAUDE_TEMPERATURE', '1.0'))
    MAX_TOKENS = int(os.getenv('CLAUDE_MAX_TOKENS', '1000'))
    TOP_P = float(os.getenv('CLAUDE_TOP_P', '1.0'))
    TOP_K = int(os.getenv('CLAUDE_TOP_K', '5'))
    
class GrokConfig:
    MODEL = GROK_MODEL
    TEMPERATURE = float(os.getenv('GROK_TEMPERATURE', '0.7'))
    MAX_TOKENS = int(os.getenv('GROK_MAX_TOKENS', '2048'))
    TOP_P = float(os.getenv('GROK_TOP_P', '0.95'))
    FREQUENCY_PENALTY = float(os.getenv('GROK_FREQUENCY_PENALTY', '0.0'))

# Summarization-specific configurations
class SummarizationConfig:
    PROVIDER = SUMMARIZATION_PROVIDER
    MODEL = SUMMARIZATION_MODEL
    
    # OpenAI summarization settings
    OPENAI_TEMPERATURE = float(os.getenv('SUMMARIZATION_OPENAI_TEMPERATURE', '0.3'))
    OPENAI_MAX_TOKENS = int(os.getenv('SUMMARIZATION_OPENAI_MAX_TOKENS', '1024'))
    
    # Google summarization settings
    GOOGLE_TEMPERATURE = float(os.getenv('SUMMARIZATION_GOOGLE_TEMPERATURE', '0.3'))
    GOOGLE_MAX_OUTPUT_TOKENS = int(os.getenv('SUMMARIZATION_GOOGLE_MAX_OUTPUT_TOKENS', '1024'))
    GOOGLE_TOP_P = float(os.getenv('SUMMARIZATION_GOOGLE_TOP_P', '0.95'))
    GOOGLE_TOP_K = int(os.getenv('SUMMARIZATION_GOOGLE_TOP_K', '40'))
    
    # Claude summarization settings
    CLAUDE_TEMPERATURE = float(os.getenv('SUMMARIZATION_CLAUDE_TEMPERATURE', '0.3'))
    CLAUDE_MAX_TOKENS = int(os.getenv('SUMMARIZATION_CLAUDE_MAX_TOKENS', '500'))
    
    # Grok summarization settings
    GROK_TEMPERATURE = float(os.getenv('SUMMARIZATION_GROK_TEMPERATURE', '0.3'))
    GROK_MAX_TOKENS = int(os.getenv('SUMMARIZATION_GROK_MAX_TOKENS', '1024'))