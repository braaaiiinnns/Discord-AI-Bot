import discord
import logging
from discord import app_commands
from config import GPT_SYSTEM_PROMPT, GOOGLE_SYSTEM_PROMPT, CLAUDE_SYSTEM_PROMPT, DEFAULT_SUMMARY_LIMIT, RESPONSE_CHANNEL_ID
from state import BotState
from utilities import route_response

class CommandGroup(app_commands.Group):  # Ensure proper inheritance from app_commands.Group
    """Command group for /ask commands."""
    def __init__(self, bot_state: BotState, logger: logging.Logger, client: discord.Client, openai_client, google_client, claude_client):
        super().__init__(name="ask", description="Ask various AI models")  # Ensure correct initialization
        self.bot_state = bot_state
        self.logger = logger
        self.client = client  # Store the client object
        self.openai_client = openai_client
        self.google_client = google_client
        self.claude_client = claude_client

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

    @app_commands.command(name="make", description="Generate an image using DALL-E 3")
    async def make_image(self, interaction: discord.Interaction, prompt: str):
        """
        Generate an image using DALL-E 3 based on the provided prompt.
        """
        self.logger.info(f"User {interaction.user} invoked /make with prompt: {prompt}")
        await interaction.response.defer()

        try:
            # Generate the image using OpenAI's DALL-E 3
            self.logger.info("Generating image using DALL-E 3...")
            response = self.openai_client.images.generate(
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
            result = await self.generate_response(context, client, system_prompt)
            user_state.add_prompt("assistant", result)

            # Determine if summarization is needed
            summary = None
            if len(result) > DEFAULT_SUMMARY_LIMIT:
                self.logger.info(f"Response exceeds {DEFAULT_SUMMARY_LIMIT} characters. Summarizing...")
                summary = await self.summarize_response(result, client)

            # Route the response using the helper function
            await route_response(interaction, prompt, result, summary, RESPONSE_CHANNEL_ID, self.logger)
        except Exception as e:
            self.logger.error(f"Error in {description} for user {interaction.user}: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while processing your request. Please try again later.")

    async def summarize_response(self, response: str, client) -> str:
        """Summarize the response to be under the DEFAULT_SUMMARY_LIMIT."""
        self.logger.info("Summarizing response...")
        summary_prompt = f"Summarize the following text to less than {DEFAULT_SUMMARY_LIMIT} characters:\n\n{response}"
        try:
            if hasattr(client, "models"):
                summary_response = client.models.generate_content(
                    model="gemini-2.0-flash", contents=summary_prompt
                )
                return summary_response.text.strip()
            else:
                self.logger.error("Summarization is only supported for Google GenAI.")
                raise AttributeError("Summarization is only supported for Google GenAI.")
        except Exception as e:
            self.logger.error(f"Error during summarization: {e}", exc_info=True)
            raise

    async def generate_response(self, context, client, system_prompt: str) -> str:
        """Generate a response using the provided client and system prompt."""
        self.logger.info("Generating response...")
        messages = [{"role": "system", "content": system_prompt}] + context

        try:
            # Handle OpenAI client
            if hasattr(client, "chat"):
                self.logger.info("Using OpenAI client for response generation.")
                response = client.chat.completions.create(model="gpt-4o-mini", messages=messages)
                return response.choices[0].message.content.strip()

            # Handle Google GenAI client
            elif hasattr(client, "models"):
                self.logger.info("Using Google GenAI client for response generation.")
                full_prompt = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])
                response = client.models.generate_content(
                    model="gemini-2.0-flash", contents=full_prompt
                )
                return response.text.strip()

            # Handle Claude client
            elif hasattr(client, "messages"):
                self.logger.info("Using Claude client for response generation.")
                response = client.messages.create(
                    model="claude-3-5-haiku-20241022",
                    max_tokens=1000,
                    temperature=1,
                    system=system_prompt,
                    messages=[{"type": "text", "text": msg["content"]} for msg in messages],
                )
                content = response.content
                if isinstance(content, list):
                    return "".join(item.text if hasattr(item, "text") else str(item) for item in content).strip()
                return content.strip()

            # Raise an error if the client is unsupported
            else:
                self.logger.error(f"Unsupported client type: {type(client).__name__}")
                raise AttributeError(f"Unsupported client type: {type(client).__name__}")
        except Exception as e:
            self.logger.error(f"Error during response generation: {e}", exc_info=True)
            raise


class CommandHandler:
    """Main command handler for registering commands."""
    def __init__(self, bot_state: BotState, tree: discord.app_commands.CommandTree):
        self.logger = logging.getLogger('discord_bot')  # Ensure consistent logger name
        self.bot_state = bot_state
        self.tree = tree

    def register_commands(self, client: discord.Client, openai_client, google_client, claude_client):
        try:
            # Register the /ask command group
            self.tree.add_command(CommandGroup(
                bot_state=self.bot_state,
                logger=self.logger,
                client=client,  # Pass the client object
                openai_client=openai_client,
                google_client=google_client,
                claude_client=claude_client
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

            # Register the /make command
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