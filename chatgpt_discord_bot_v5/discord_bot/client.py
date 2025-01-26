
import discord
from discord_bot.commands import handle_message

intents = discord.Intents.default()
intents.message_content = True
discord_client = discord.Client(intents=intents)

@discord_client.event
async def on_message(message):
    await handle_message(message, discord_client)
