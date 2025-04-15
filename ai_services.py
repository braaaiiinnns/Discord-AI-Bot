from abc import ABC, abstractmethod
import logging
import openai

logger = logging.getLogger('discord_bot')

# Client factory functions

def get_openai_client(api_key):
    """Initialize and return an OpenAI client"""
    openai.api_key = api_key
    return openai

def get_google_genai_client(api_key):
    """Initialize and return a Google GenAI client"""
    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except ImportError as e:
        logger.error("Google GenAI library not installed. Please install google-genai.")
        return None

def get_claude_client(api_key):
    """Initialize and return a Claude/Anthropic client"""
    try:
        import anthropic
        return anthropic.Client(api_key=api_key)
    except ImportError as e:
        logger.error("Anthropic API library not installed. Please install anthropic.")
        return None

def get_grok_client(api_key):
    """Initialize and return a Grok client (using OpenAI compatible SDK)"""
    try:
        import openai as grok_client
        grok_client.api_key = api_key
        grok_client.api_base = "https://api.x.ai/v1"
        return grok_client
    except ImportError as e:
        logger.error("OpenAI library not installed. Please install openai.")
        return None

# Client strategy classes for generating responses

class AIClientStrategy(ABC):
    """Abstract base class for AI client strategies."""
    def __init__(self, client, logger):
        self.client = client
        self.logger = logger

    @abstractmethod
    async def generate_response(self, context: list, system_prompt: str) -> str:
        """Generate a response using the provided context and system prompt"""
        pass

class OpenAIStrategy(AIClientStrategy):
    """Strategy for generating responses using OpenAI's API"""
    async def generate_response(self, context: list, system_prompt: str) -> str:
        self.logger.info("Using OpenAI client for response generation.")
        messages = [{"role": "system", "content": system_prompt}] + context
        
        response = self.client.ChatCompletion.create(
            model="gpt-4o-mini", 
            messages=messages
        )
        return response.choices[0].message.content.strip()

class GoogleGenAIStrategy(AIClientStrategy):
    """Strategy for generating responses using Google's Gemini API"""
    async def generate_response(self, context: list, system_prompt: str) -> str:
        full_prompt = "\n".join([f"{msg['role']}: {msg['content']}" for msg in context])
        self.logger.info("Using Google GenAI client for response generation.")
        response = self.client.models.generate_content(
            model="gemini-2.0-flash",
            contents=full_prompt
        )
        return response.text.strip()

class ClaudeStrategy(AIClientStrategy):
    """Strategy for generating responses using Anthropic's Claude API"""
    async def generate_response(self, context: list, system_prompt: str) -> str:
        self.logger.info("Using Claude client with Messages API for response generation.")
        
        # Build the user messages (exclude the system prompt)
        user_messages = context

        # Call the Messages API with the correct arguments
        response = self.client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1000,
            temperature=1,
            system=system_prompt,
            messages=user_messages
        )

        # Access the generated content from the response
        if hasattr(response, "content"):
            if isinstance(response.content, list):
                # Concatenate all TextBlock objects into a single string
                return "".join(block.text if hasattr(block, "text") else str(block) for block in response.content).strip()
            return response.content.strip()
        else:
            self.logger.error("Claude API response does not contain 'content'.")
            raise ValueError("Claude API response does not contain 'content'.")

class GrokStrategy(AIClientStrategy):
    """Strategy for generating responses using xAI's Grok API"""
    async def generate_response(self, context: list, system_prompt: str) -> str:
        self.logger.info("Using xAI/Grok client with OpenAI SDK for response generation.")
        messages = [{"role": "system", "content": system_prompt}] + context
        
        response = self.client.ChatCompletion.create(
            model="grok-3-beta",
            messages=messages,
            temperature=0.7,
            max_tokens=2048
        )
        return response.choices[0].message.content.strip()