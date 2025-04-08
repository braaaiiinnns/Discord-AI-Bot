import discord
import logging  # Ensure logging is imported
from discord import app_commands
from discord.utils import get  # Import utility for searching channels
from config import DISCORD_BOT_TOKEN, OPENAI_API_KEY, GOOGLE_GENAI_API_KEY, CLAUDE_API_KEY
from logger_config import setup_logger
from clients import get_openai_client, get_google_genai_client, get_claude_client
from state import BotState
from commands import CommandHandler, CommandGroup  # Import CommandGroup

class DiscordBot:
    def __init__(self):
        self.logger = setup_logger()  # Ensure logger is initialized using setup_logger
        
        # Configure intents
        self.intents = discord.Intents.all()  # Initialize intents
        # Alternatively, uncomment the following lines to customize intents:
        # self.intents.messages = True  # Enable message-related events
        # self.intents.guilds = True    # Enable guild-related events
        # self.intents.message_content = True  # Enable access to message content (required for some commands)
        # self.intents.members = True   # Enable member-related events (if needed)

        self.client = discord.AutoShardedClient(intents=self.intents)
        self.tree = app_commands.CommandTree(self.client)
        self.bot_state = BotState(timeout=3600)
        self.response_channels = {}  # Cache response channels by guild ID

        # Pass response_channels to CommandHandler
        self.command_handler = CommandHandler(self.bot_state, self.tree, self.response_channels, self.logger)

        # Initialize API clients
        self.openai_client = get_openai_client(OPENAI_API_KEY)
        self.google_client = get_google_genai_client(GOOGLE_GENAI_API_KEY)
        self.claude_client = get_claude_client(CLAUDE_API_KEY)

        # Register commands
        self.command_handler.register_commands(
            self.client, self.openai_client, self.google_client, self.claude_client
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

            # Log registered commands after syncing
            self.logger.info("Registered commands:")
            for command in self.tree.get_commands():
                self.logger.info(f"- {command.name}")

            # Search for or create the "🤖" channel in all guilds
            for guild in self.client.guilds:
                response_channel = discord.utils.get(guild.text_channels, name="🤖")
                if response_channel:
                    self.logger.info(f"Response channel found: {response_channel.name} (ID: {response_channel.id}) in guild {guild.name}")
                else:
                    try:
                        response_channel = await guild.create_text_channel("🤖")
                        self.logger.info(f"Created response channel: {response_channel.name} (ID: {response_channel.id}) in guild {guild.name}")
                    except Exception as e:
                        self.logger.error(f"Failed to create response channel in guild {guild.name}: {e}", exc_info=True)

                # Cache the response channel for the guild
                self.response_channels[guild.id] = response_channel

                self.logger.info(f"Response channel cached for guild '{guild.name}': {response_channel.name} (ID: {response_channel.id})")

        # Run the bot
        self.client.run(DISCORD_BOT_TOKEN)

class CommandHandler:
    """Main command handler for registering commands."""
    def __init__(self, bot_state: BotState, tree: discord.app_commands.CommandTree, response_channels: dict, logger: logging.Logger):
        self.logger = logger  # Use the logger passed from DiscordBot
        self.bot_state = bot_state
        self.tree = tree
        self.response_channels = response_channels  # Store response_channels

    def register_commands(self, client: discord.Client, openai_client, google_client, claude_client):
        # Register the /ask command group
        self.tree.add_command(CommandGroup(
            bot_state=self.bot_state,
            logger=self.logger,
            client=client,  # Pass the client object
            openai_client=openai_client,
            google_client=google_client,
            claude_client=claude_client,
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

if __name__ == "__main__":
    bot = DiscordBot()
    bot.run()