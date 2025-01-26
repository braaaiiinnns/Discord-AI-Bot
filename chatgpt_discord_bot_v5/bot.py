
from discord_bot.client import discord_client
from config.env import load_env
from config.logging import setup_logging

# Load environment variables and logging
load_env()
setup_logging()

# Run the bot
discord_client.run(os.getenv("DISCORD_BOT_TOKEN"))
