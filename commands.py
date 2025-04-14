import discord
import logging
from discord import app_commands
from config import GPT_SYSTEM_PROMPT, GOOGLE_SYSTEM_PROMPT, CLAUDE_SYSTEM_PROMPT, GROK_SYSTEM_PROMPT, DEFAULT_SUMMARY_LIMIT, RESPONSE_CHANNEL_ID
from state import BotState
from utilities import route_response
from ai_clients import OpenAIStrategy, GoogleGenAIStrategy, ClaudeStrategy, GrokStrategy

class CommandGroup(app_commands.Group):  # Ensure proper inheritance from app_commands.Group
    """Command group for /ask commands."""
    def __init__(self, bot_state: BotState, logger: logging.Logger, client: discord.Client, openai_client, google_client, claude_client, grok_client, response_channels: dict):
        super().__init__(name="ask", description="Ask various AI models")  # Ensure correct initialization
        self.bot_state = bot_state
        self.logger = logger
        self.client = client  # Store the client object
        self.openai_client = openai_client
        self.google_client = google_client
        self.claude_client = claude_client
        self.grok_client = grok_client
        self.response_channels = response_channels  # Store response channels

    @app_commands.command(name="gpt", description="Ask GPT-4o-mini a question")
    async def ask_gpt(self, interaction: discord.Interaction, question: str):
        await self.handle_prompt_command(
            interaction, question, self.openai_client, "GPT-4o-mini", GPT_SYSTEM_PROMPT
        )

    @app_commands.command(name="google", description="Ask Google GenAI a question")
    async def ask_google(self, interaction: discord.Interaction, question: str):
        await self.handle_prompt_command(
            interaction, question, self.google_client, "Google GenAI", GOOGLE_SYSTEM_PROMPT
        )

    @app_commands.command(name="claude", description="Ask Claude (as a poet) a question")
    async def ask_claude(self, interaction: discord.Interaction, question: str):
        await self.handle_prompt_command(
            interaction, question, self.claude_client, "Claude", CLAUDE_SYSTEM_PROMPT
        )
        
    @app_commands.command(name="grok", description="Ask Grok a witty question")
    async def ask_grok(self, interaction: discord.Interaction, question: str):
        await self.handle_prompt_command(
            interaction, question, self.grok_client, "Grok", GROK_SYSTEM_PROMPT
        )

    async def handle_prompt_command(self, interaction: discord.Interaction, prompt: str, client, description: str, system_prompt: str):
        """Handle a prompt-based command."""
        self.logger.info(f"Handling {description} for user {interaction.user} with prompt: {prompt}")
        uid = str(interaction.user.id)
        user_state = self.bot_state.get_user_state(uid)
        user_state.add_prompt("user", prompt)
        context = user_state.get_context()

        await interaction.response.defer()
        try:
            self.logger.info(f"Generating response for {description}...")

            # Select the appropriate strategy
            if description == "GPT-4o-mini":
                strategy = OpenAIStrategy(client, self.logger)  # Pass the logger to the base class
            elif description == "Google GenAI":
                strategy = GoogleGenAIStrategy(client, self.logger)  # Pass the logger to the base class
            elif description == "Claude":
                strategy = ClaudeStrategy(client, self.logger)  # Pass the logger to the base class
            elif description == "Grok":
                strategy = GrokStrategy(client, self.logger)  # Pass the logger to the base class
            else:
                raise ValueError(f"Unsupported AI model: {description}")

            # Generate the response using the strategy
            result = await strategy.generate_response(context, system_prompt)  # Await the coroutine

            user_state.add_prompt("assistant", result)

            # Determine if summarization is needed
            summary = None
            if len(result) > DEFAULT_SUMMARY_LIMIT:
                self.logger.info(f"Response exceeds {DEFAULT_SUMMARY_LIMIT} characters. Summarizing...")
                summary = await self.summarize_response(result)

            # Route the response using the helper function
            await route_response(interaction, prompt, result, summary, self.response_channels, self.logger)  # Use self.response_channels
        except Exception as e:
            self.logger.error(f"Error in {description} for user {interaction.user}: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while processing your request. Please try again later.")

    async def summarize_response(self, response: str) -> str:
        """Summarize the response to be under the DEFAULT_SUMMARY_LIMIT using GoogleGenAIStrategy."""
        self.logger.info("Summarizing response...")
        summary_prompt = f"Summarize the following text to less than {DEFAULT_SUMMARY_LIMIT} characters:\n\n{response}"
        try:
            # Always use GoogleGenAIStrategy for summarization
            google_strategy = GoogleGenAIStrategy(self.google_client, self.logger)
            return await google_strategy.generate_response([{"role": "user", "content": summary_prompt}], GOOGLE_SYSTEM_PROMPT)
        except Exception as e:
            self.logger.error(f"Error during summarization: {e}", exc_info=True)
            raise


class CommandHandler:
    """Main command handler for registering commands."""
    def __init__(self, bot_state: BotState, tree: discord.app_commands.CommandTree, response_channels: dict, logger: logging.Logger):
        self.logger = logger  # Ensure consistent logger name
        self.bot_state = bot_state
        self.tree = tree
        self.response_channels = response_channels  # Cache response channels

    def register_commands(self, client: discord.Client, openai_client, google_client, claude_client, grok_client):
        try:
            # Register the /ask command group
            self.tree.add_command(CommandGroup(
                bot_state=self.bot_state,
                logger=self.logger,
                client=client,  # Pass the client object
                openai_client=openai_client,
                google_client=google_client,
                claude_client=claude_client,
                grok_client=grok_client,  # Pass the Grok client
                response_channels=self.response_channels  # Pass the response channels
            ))
            self.logger.info("Registered /ask command group.")

            # Register the /clear_history command
            @self.tree.command(name="clear_history", description="Clear your conversation history")
            async def clear_history(interaction: discord.Interaction):
                self.logger.info(f"User {interaction.user} invoked /clear_history")
                uid = str(interaction.user.id)
                user_state = self.bot_state.get_user_state(uid)
                user_state.clear_history()
                self.logger.info(f"Cleared history for user {interaction.user}")
                await interaction.response.send_message("Your conversation history has been cleared.")

            # Register the /make command as a standalone command
            @self.tree.command(name="make", description="Generate an image using DALL-E 3")
            async def make_image(interaction: discord.Interaction, prompt: str):
                self.logger.info(f"User {interaction.user} invoked /make with prompt: {prompt}")
                await interaction.response.defer()

                try:
                    # Generate the image using OpenAI's DALL-E 3
                    self.logger.info("Generating image using DALL-E 3...")
                    response = openai_client.images.generate(
                        prompt=prompt,
                        n=1,  # Generate one image
                        size="1024x1024"  # Specify the image size
                    )
                    image_url = response['data'][0]['url']
                    self.logger.info(f"Image generated successfully: {image_url}")

                    # Send the image URL to the user
                    await interaction.followup.send(f"Here is your generated image:\n{image_url}")
                except Exception as e:
                    self.logger.error(f"Error generating image: {e}", exc_info=True)
                    await interaction.followup.send("An error occurred while generating the image. Please try again later.")
        except Exception as e:
            self.logger.error(f"Failed to register commands: {e}", exc_info=True)