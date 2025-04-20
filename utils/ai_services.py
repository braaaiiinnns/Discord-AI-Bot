from abc import ABC, abstractmethod
import logging
import openai
from openai import OpenAI

logger = logging.getLogger('discord_bot')

# Client factory functions

def get_openai_client(api_key):
    """Initialize and return an OpenAI client"""
    logger.debug("Attempting to initialize OpenAI client.")
    if not api_key:
        logger.debug("No OpenAI API key provided. Client not initialized.") # Change to debug
        return None
    try:
        client = OpenAI(api_key=api_key)
        logger.debug("OpenAI client initialized successfully.")
        return client
    except Exception as e:
        logger.error(f"Error initializing OpenAI client: {str(e)}", exc_info=True)
        return None

def get_google_genai_client(api_key):
    """Initialize and return a Google GenAI client"""
    logger.debug("Attempting to initialize Google GenAI client.")
    if not api_key:
        logger.debug("No Google GenAI API key provided. Client not initialized.") # Change to debug
        return None
        
    try:
        from google import genai
        logger.debug("Imported google.genai successfully.")
        # Initialize the client with API key
        client = genai.Client(api_key=api_key)
        logger.debug("Google GenAI client initialized successfully.")
        return client
    except ImportError as e:
        logger.error(f"Google GenAI library not installed: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error initializing Google GenAI client: {str(e)}", exc_info=True)
        return None

def get_claude_client(api_key):
    """Initialize and return a Claude/Anthropic client"""
    logger.debug("Attempting to initialize Claude client.")
    if not api_key:
        logger.debug("No Claude API key provided. Client not initialized.") # Change to debug
        return None
        
    try:
        import anthropic
        logger.debug("Imported anthropic successfully.")
        client = anthropic.Client(api_key=api_key)
        logger.debug("Claude client initialized successfully.")
        return client
    except ImportError as e:
        logger.error("Anthropic API library not installed. Please install anthropic.")
        return None
    except Exception as e:
        logger.error(f"Error initializing Claude client: {str(e)}", exc_info=True)
        return None

def get_grok_client(api_key):
    """Initialize and return a Grok client (using OpenAI compatible SDK)"""
    logger.debug("Attempting to initialize Grok client.")
    if not api_key:
        logger.debug("No Grok API key provided. Client not initialized.") # Change to debug
        return None
        
    try:
        from openai import OpenAI as GrokClient
        logger.debug("Imported GrokClient (OpenAI) successfully.")
        client = GrokClient(api_key=api_key, base_url="https://api.x.ai/v1")
        logger.debug("Grok client initialized successfully.")
        return client
    except ImportError as e:
        logger.error("OpenAI library not installed. Please install openai.")
        return None
    except Exception as e:
        logger.error(f"Error initializing Grok client: {str(e)}", exc_info=True)
        return None

# Client strategy classes for generating responses

class AIClientStrategy(ABC):
    """Abstract base class for AI client strategies."""
    def __init__(self, client, logger):
        self.client = client
        self.logger = logger
        self.logger.debug(f"Initialized {self.__class__.__name__}.")

    @abstractmethod
    async def generate_response(self, context: list, system_prompt: str) -> str:
        """Generate a response using the provided context and system prompt"""
        pass

class OpenAIStrategy(AIClientStrategy):
    """Strategy for generating responses using OpenAI's API"""
    async def generate_response(self, context: list, system_prompt: str) -> str:
        self.logger.debug(f"OpenAIStrategy generating response. Context length: {len(context)}")
        if not self.client:
            self.logger.error("OpenAI client not initialized")
            return "Sorry, I cannot generate a response because the OpenAI API is not configured."
            
        messages = [{"role": "system", "content": system_prompt}] + context
        self.logger.debug(f"Sending {len(messages)} messages to OpenAI API.")
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini", 
                messages=messages
            )
            self.logger.debug("Received response from OpenAI API.")
            result = response.choices[0].message.content.strip()
            self.logger.debug(f"OpenAI response length: {len(result)}")
            return result
        except Exception as e:
            self.logger.error(f"Error during OpenAI API call: {str(e)}", exc_info=True)
            return f"Sorry, an error occurred while contacting OpenAI: {str(e)}"

class GoogleGenAIStrategy(AIClientStrategy):
    """Strategy for generating responses using Google's Gemini API"""
    async def generate_response(self, context: list, system_prompt: str) -> str:
        self.logger.debug(f"GoogleGenAIStrategy generating response. Context length: {len(context)}")
        if not self.client:
            self.logger.error("Google GenAI client not initialized")
            return "Sorry, I cannot generate a response because the Google GenAI API is not configured."
        
        try:
            # Format messages into a single prompt with clear role indicators
            formatted_content = f"System: {system_prompt}\n\nYou are Gemini, a helpful, detailed, and informative AI assistant. Provide comprehensive, in-depth responses to user queries.\n\n"
            
            for message in context:
                role = message["role"]
                content = message["content"]
                if role == "user":
                    formatted_content += f"User: {content}\n\n"
                elif role == "assistant":
                    formatted_content += f"Assistant: {content}\n\n"
            
            # For the last user message, ensure we're asking for a detailed response
            if context and context[-1]["role"] == "user":
                formatted_content += "Assistant: "
            
            self.logger.debug("Formatted context for Google GenAI API.")
            
            # Generate the response using the documented approach
            self.logger.debug("Sending request to Google GenAI API.")
            
            # Import the types module from Google GenAI
            from google.genai import types
            
            # Create config object with settings for longer responses
            generation_config = types.GenerateContentConfig(
                temperature=0.8,
                max_output_tokens=4096,  # Increased from 2048
                top_p=0.95,
                top_k=64  # Increased from 40
            )
            
            response = self.client.models.generate_content(
                model="gemini-1.5-pro",  # Using the pro model instead of flash for more detailed responses
                contents=formatted_content,
                config=generation_config
            )
            
            self.logger.debug("Received response from Google GenAI API.")
            
            # Extract the text from the response
            if hasattr(response, "text"):
                result = response.text.strip()
                
                # Clean up potential prefixes in the response
                if result.startswith("Assistant:"):
                    result = result[len("Assistant:"):].strip()
                
                self.logger.debug(f"Google GenAI response length: {len(result)}")
                return result
            else:
                self.logger.warning("Response doesn't have a 'text' attribute, trying alternative extraction")
                result = str(response)
                
                # Try to extract just the content part
                if "text:" in result:
                    result = result.split("text:")[1].strip()
                
                self.logger.debug(f"Google GenAI response (fallback extraction) length: {len(result)}")
                return result
        except Exception as e:
            self.logger.error(f"Error in Google GenAI: {str(e)}", exc_info=True)
            return f"Sorry, an error occurred while contacting Google GenAI: {str(e)}"

class ClaudeStrategy(AIClientStrategy):
    """Strategy for generating responses using Anthropic's Claude API"""
    async def generate_response(self, context: list, system_prompt: str) -> str:
        self.logger.debug(f"ClaudeStrategy generating response. Context length: {len(context)}")
        if not self.client:
            self.logger.error("Claude client not initialized")
            return "Sorry, I cannot generate a response because the Claude API is not configured."
            
        # Build the user messages (exclude the system prompt)
        user_messages = context
        self.logger.debug(f"Sending {len(user_messages)} messages to Claude API.")

        try:
            # Call the Messages API with the correct arguments
            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1000,
                temperature=1,
                system=system_prompt,
                messages=user_messages
            )
            self.logger.debug("Received response from Claude API.")

            # Access the generated content from the response
            if hasattr(response, "content"):
                if isinstance(response.content, list):
                    # Concatenate all TextBlock objects into a single string
                    result = "".join(block.text if hasattr(block, "text") else str(block) for block in response.content).strip()
                    self.logger.debug(f"Claude response length (list): {len(result)}")
                    return result
                result = response.content.strip()
                self.logger.debug(f"Claude response length (single): {len(result)}")
                return result
            else:
                self.logger.error("Claude API response does not contain 'content'.")
                return "Sorry, the response from Claude was malformed."
        except Exception as e:
            self.logger.error(f"Error during Claude API call: {str(e)}", exc_info=True)
            return f"Sorry, an error occurred while contacting Claude: {str(e)}"

class GrokStrategy(AIClientStrategy):
    """Strategy for generating responses using xAI's Grok API"""
    async def generate_response(self, context: list, system_prompt: str) -> str:
        self.logger.debug(f"GrokStrategy generating response. Context length: {len(context)}")
        if not self.client:
            self.logger.error("Grok client not initialized")
            return "Sorry, I cannot generate a response because the Grok API is not configured."
            
        messages = [{"role": "system", "content": system_prompt}] + context
        self.logger.debug(f"Sending {len(messages)} messages to Grok API.")
        
        try:
            # Updated to use the new API pattern
            response = self.client.chat.completions.create(
                model="grok-3-beta",
                messages=messages,
                temperature=0.7,
                max_tokens=2048
            )
            self.logger.debug("Received response from Grok API.")
            result = response.choices[0].message.content.strip()
            self.logger.debug(f"Grok response length: {len(result)}")
            return result
        except Exception as e:
            self.logger.error(f"Error during Grok API call: {str(e)}", exc_info=True)
            return f"Sorry, an error occurred while contacting Grok: {str(e)}"