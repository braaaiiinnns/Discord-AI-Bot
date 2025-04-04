import discord
import logging
from utilities import compose_text_response, split_message
from config import GPT_SYSTEM_PROMPT, GOOGLE_SYSTEM_PROMPT, CLAUDE_SYSTEM_PROMPT
from state import BotState

class CommandGroup(discord.app_commands.Group):
    """Base class for command groups."""
    def __init__(self, name: str, description: str, bot_state: BotState, logger: logging.Logger):
        super().__init__(name=name, description=description)
        self.bot_state = bot_state
        self.logger = logger

    async def handle_prompt_command(self, interaction, prompt, client, description, system_prompt):
        """Handle a prompt-based command."""
        self.logger.info(f"Handling {description} for user {interaction.user} with prompt: {prompt}")
        uid = str(interaction.user.id)
        user_state = self.bot_state.get_user_state(uid)
        user_state.add_prompt("user", prompt)
        context = user_state.get_context()

        await interaction.response.defer()
        try:
            result = await self.generate_response(context, client, system_prompt)
            user_state.add_prompt("assistant", result)
            self.logger.info(f"Generated response for {description}: {result}")
            await interaction.followup.send(result)
        except Exception as e:
            self.logger.error(f"Error in {description} for user {interaction.user}: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while processing your request. Please try again later.")

    async def generate_response(self, context, client, system_prompt):
        """Generate a response using the provided client and system prompt."""
        messages = [{"role": "system", "content": system_prompt}] + context
        response = client.chat.completions.create(model="gpt-4o-mini", messages=messages)
        return response.choices[0].message.content.strip()


class AskCommandGroup(CommandGroup):
    """Command group for /ask commands."""
    def __init__(self, bot_state: BotState, logger: logging.Logger, openai_client, google_client, claude_client):
        super().__init__(name="ask", description="Ask various AI models", bot_state=bot_state, logger=logger)
        self.openai_client = openai_client
        self.google_client = google_client
        self.claude_client = claude_client

        @self.command(name="gpt", description="Ask GPT-4o-mini a question")
        async def ask_gpt(interaction: discord.Interaction, question: str):
            await self.handle_prompt_command(
                interaction, question, self.openai_client, "GPT-4o-mini", GPT_SYSTEM_PROMPT
            )

        @self.command(name="google", description="Ask Google GenAI a question")
        async def ask_google(interaction: discord.Interaction, question: str):
            await self.handle_prompt_command(
                interaction, question, self.google_client, "Google GenAI", GOOGLE_SYSTEM_PROMPT
            )

        @self.command(name="claude", description="Ask Claude (as a poet) a question")
        async def ask_claude(interaction: discord.Interaction, question: str):
            await self.handle_prompt_command(
                interaction, question, self.claude_client, "Claude", CLAUDE_SYSTEM_PROMPT
            )


class CommandHandler:
    """Main command handler for registering commands."""
    def __init__(self, bot_state: BotState, tree):
        self.logger = logging.getLogger('discord_bot')
        self.bot_state = bot_state
        self.tree = tree

    def register_commands(self, openai_client, google_client, claude_client):
        # Register the /ask command group
        ask_group = AskCommandGroup(self.bot_state, self.logger, openai_client, google_client, claude_client)
        self.tree.add_command(ask_group)

        # Register the /clear_history command
        @self.tree.command(name="clear_history", description="Clear your conversation history")
        async def clear_history(interaction: discord.Interaction):
            self.logger.info(f"User {interaction.user} invoked /clear_history")
            uid = str(interaction.user.id)
            user_state = self.bot_state.get_user_state(uid)
            user_state.clear_history()
            self.logger.info(f"Cleared history for user {interaction.user}")
            await interaction.response.send_message("Your conversation history has been cleared.")