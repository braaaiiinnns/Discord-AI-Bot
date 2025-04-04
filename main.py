import discord
from discord import app_commands
import logging
from config import DISCORD_BOT_TOKEN, OPENAI_API_KEY, GOOGLE_GENAI_API_KEY, CLAUDE_API_KEY
from logger_config import setup_logger
from clients import get_openai_client, get_google_genai_client, get_claude_client
from state import BotState
from commands import CommandHandler

class DiscordBot:
    def __init__(self):
        self.logger = setup_logger()
        self.intents = discord.Intents.all()
        self.client = discord.Client(intents=self.intents)
        self.tree = app_commands.CommandTree(self.client)
        self.bot_state = BotState(timeout=3600)
        self.command_handler = CommandHandler(self.bot_state, self.tree)

        # Initialize API clients
        self.openai_client = get_openai_client(OPENAI_API_KEY)
        self.google_client = get_google_genai_client(GOOGLE_GENAI_API_KEY)
        self.claude_client = get_claude_client(CLAUDE_API_KEY)

    def run(self):
        @self.client.event
        async def on_ready():
            await self.tree.sync()  # Sync commands globally
            self.logger.info(f"Logged in as {self.client.user}")
            self.logger.info("Registered commands:")
            for command in self.tree.get_commands():
                self.logger.info(f"- {command.name}")

        # Register commands
        self.command_handler.register_commands(
            self.openai_client, self.google_client, self.claude_client
        )

        # Run the bot
        self.client.run(DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    bot = DiscordBot()
    bot.run()