import discord
import logging  # Ensure logging is imported
from discord import app_commands
from config import DISCORD_BOT_TOKEN, OPENAI_API_KEY, GOOGLE_GENAI_API_KEY, CLAUDE_API_KEY
from logger_config import setup_logger
from clients import get_openai_client, get_google_genai_client, get_claude_client
from state import BotState
from commands import CommandHandler, CommandGroup  # Import CommandGroup

class DiscordBot:
    def __init__(self):
        self.logger = setup_logger()  # Ensure logger is initialized using setup_logger
        
        # Configure intents
        # self.intents = discord.Intents.all()
        self.intents.messages = True  # Enable message-related events
        self.intents.guilds = True    # Enable guild-related events
        self.intents.message_content = True  # Enable access to message content (required for some commands)
        self.intents.members = True   # Enable member-related events (if needed)

        self.client = discord.AutoShardedClient(intents=self.intents)
        self.tree = app_commands.CommandTree(self.client)
        self.bot_state = BotState(timeout=3600)
        self.command_handler = CommandHandler(self.bot_state, self.tree)

        # Initialize API clients
        self.openai_client = get_openai_client(OPENAI_API_KEY)
        self.google_client = get_google_genai_client(GOOGLE_GENAI_API_KEY)
        self.claude_client = get_claude_client(CLAUDE_API_KEY)

        # Register commands
        self.command_handler.register_commands(
            self.openai_client, self.google_client, self.claude_client
        )

    def run(self):
        @self.client.event
        async def on_ready():
            self.logger.info(f"Logged in as {self.client.user}")
            self.logger.info("Syncing commands with Discord...")
            try:
                # Sync commands globally
                await self.tree.sync()
                self.logger.info("Commands synced successfully.")
            except Exception as e:
                self.logger.error(f"Failed to sync commands: {e}", exc_info=True)

            # Ensure the bot's cache is fully populated
            if not self.client.guilds:
                self.logger.warning("No guilds found. Ensure the bot is invited to a server.")
            else:
                # Update the list of connected guilds
                self.bot_state.guilds = self.client.guilds
                self.logger.info("Connected guilds:")
                for guild in self.client.guilds:
                    self.logger.info(f"- {guild.name} (ID: {guild.id})")

            self.logger.info("Registered commands:")
            for command in self.tree.get_commands():
                self.logger.info(f"- {command.name}")

        # Run the bot
        self.client.run(DISCORD_BOT_TOKEN)

class CommandHandler:
    """Main command handler for registering commands."""
    def __init__(self, bot_state: BotState, tree: discord.app_commands.CommandTree):
        self.logger = logging.getLogger('discord_bot')  # Ensure consistent logger name
        self.bot_state = bot_state
        self.tree = tree

    def register_commands(self, openai_client, google_client, claude_client):
        # Register the /ask command group
        self.tree.add_command(CommandGroup(
            bot_state=self.bot_state,
            logger=self.logger,
            client=self.tree.client,  # Pass the client object
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

if __name__ == "__main__":
    bot = DiscordBot()
    bot.run()