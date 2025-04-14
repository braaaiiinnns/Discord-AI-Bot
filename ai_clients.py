from abc import ABC, abstractmethod

class AIClientStrategy(ABC):
    """Abstract base class for AI client strategies."""
    def __init__(self, logger):
        self.logger = logger  # Initialize the logger in the base class

    @abstractmethod
    async def generate_response(self, context: list, system_prompt: str) -> str:
        pass

class OpenAIStrategy(AIClientStrategy):
    def __init__(self, client, logger):
        super().__init__(logger)  # Pass the logger to the base class
        self.client = client

    async def generate_response(self, context: list, system_prompt: str) -> str:
        """Generate a response using the OpenAI client."""
        self.logger.info("Using OpenAI client for response generation.")
        messages = [{"role": "system", "content": system_prompt}] + context
        
        # For older versions of openai library (< 1.0.0)
        response = self.client.ChatCompletion.create(
            model="gpt-4o-mini", 
            messages=messages
        )
        return response.choices[0].message.content.strip()

class GoogleGenAIStrategy(AIClientStrategy):
    def __init__(self, client, logger):
        super().__init__(logger)  # Pass the logger to the base class
        self.client = client

    async def generate_response(self, context: list, system_prompt: str) -> str:
        """Generate a response using the Google GenAI client."""
        full_prompt = "\n".join([f"{msg['role']}: {msg['content']}" for msg in context])
        self.logger.info("Using Google GenAI client for response generation.")
        response = self.client.models.generate_content(
            model="gemini-2.0-flash",
            contents=full_prompt
        )
        return response.text.strip()

class ClaudeStrategy(AIClientStrategy):
    def __init__(self, client, logger):
        super().__init__(logger)  # Pass the logger to the base class
        self.client = client

    async def generate_response(self, context: list, system_prompt: str) -> str:
        """Generate a response using the Anthropic Messages API."""
        self.logger.info("Using Claude client with Messages API for response generation.")
        
        # Build the user messages (exclude the system prompt)
        user_messages = context

        # Call the Messages API with the correct arguments
        response = self.client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1000,  # Corrected argument name
            temperature=1,
            system=system_prompt,  # Pass the system prompt as a top-level parameter
            messages=user_messages  # Pass only user messages
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
    def __init__(self, client, logger):
        super().__init__(logger)  # Pass the logger to the base class
        self.client = client

    async def generate_response(self, context: list, system_prompt: str) -> str:
        """Generate a response using the xAI/Grok client with OpenAI SDK."""
        self.logger.info("Using xAI/Grok client with OpenAI SDK for response generation.")
        messages = [{"role": "system", "content": system_prompt}] + context
        
        # For older versions of openai library (< 1.0.0)
        response = self.client.ChatCompletion.create(
            model="grok-3-beta",  # Updated to use the latest Grok model
            messages=messages,
            temperature=0.7,
            max_tokens=2048
        )
        return response.choices[0].message.content.strip()
