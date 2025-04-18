from abc import ABC, abstractmethod
import logging
import openai
from openai import OpenAI

logger = logging.getLogger('discord_bot')

# Client factory functions

def get_openai_client(api_key):
    """Initialize and return an OpenAI client"""
    if not api_key:
        logger.warning("No OpenAI API key provided")
        return None
    # Updated to use the new client approach
    return OpenAI(api_key=api_key)

def get_google_genai_client(api_key):
    """Initialize and return a Google GenAI client"""
    if not api_key:
        logger.warning("No Google GenAI API key provided")
        return None
        
    try:
        from google import genai
        
        # Initialize the client with API key
        client = genai.Client(api_key=api_key)
        
        # Test the client
        logger.info("Google GenAI client initialized successfully")
        return client
    except ImportError as e:
        logger.error(f"Google GenAI library not installed: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error initializing Google GenAI client: {str(e)}")
        return None

def get_claude_client(api_key):
    """Initialize and return a Claude/Anthropic client"""
    if not api_key:
        logger.warning("No Claude API key provided")
        return None
        
    try:
        import anthropic
        return anthropic.Client(api_key=api_key)
    except ImportError as e:
        logger.error("Anthropic API library not installed. Please install anthropic.")
        return None

def get_grok_client(api_key):
    """Initialize and return a Grok client (using OpenAI compatible SDK)"""
    if not api_key:
        logger.warning("No Grok API key provided")
        return None
        
    try:
        from openai import OpenAI as GrokClient
        return GrokClient(api_key=api_key, base_url="https://api.x.ai/v1")
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
        
        if not self.client:
            self.logger.error("OpenAI client not initialized")
            return "Sorry, I cannot generate a response because the OpenAI API is not configured."
            
        messages = [{"role": "system", "content": system_prompt}] + context
        
        # Updated to use the new API pattern
        response = self.client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=messages
        )
        return response.choices[0].message.content.strip()

class GoogleGenAIStrategy(AIClientStrategy):
    """Strategy for generating responses using Google's Gemini API"""
    async def generate_response(self, context: list, system_prompt: str) -> str:
        self.logger.info("Using Google GenAI client for response generation.")
        
        if not self.client:
            self.logger.error("Google GenAI client not initialized")
            return "Sorry, I cannot generate a response because the Google GenAI API is not configured."
        
        try:
            # Format messages into a single prompt with clear role indicators
            formatted_content = f"System: {system_prompt}\n\n"
            
            for message in context:
                role = message["role"]
                content = message["content"]
                if role == "user":
                    formatted_content += f"User: {content}\n\n"
                elif role == "assistant":
                    formatted_content += f"Assistant: {content}\n\n"
            
            # Generate the response using the exact pattern from the example
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=formatted_content
            )
            
            # Extract the text from the response
            if hasattr(response, "text"):
                return response.text.strip()
            else:
                self.logger.warning("Response doesn't have a 'text' attribute, trying alternative extraction")
                return str(response)
        except Exception as e:
            self.logger.error(f"Error in Google GenAI: {str(e)}")
            raise

class ClaudeStrategy(AIClientStrategy):
    """Strategy for generating responses using Anthropic's Claude API"""
    async def generate_response(self, context: list, system_prompt: str) -> str:
        self.logger.info("Using Claude client with Messages API for response generation.")
        
        if not self.client:
            self.logger.error("Claude client not initialized")
            return "Sorry, I cannot generate a response because the Claude API is not configured."
            
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
        
        if not self.client:
            self.logger.error("Grok client not initialized")
            return "Sorry, I cannot generate a response because the Grok API is not configured."
            
        messages = [{"role": "system", "content": system_prompt}] + context
        
        # Updated to use the new API pattern
        response = self.client.chat.completions.create(
            model="grok-3-beta",
            messages=messages,
            temperature=0.7,
            max_tokens=2048
        )
        return response.choices[0].message.content.strip()