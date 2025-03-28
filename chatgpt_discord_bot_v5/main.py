import discord
from discord import app_commands
import logging
from config import DISCORD_BOT_TOKEN, OPENAI_API_KEY, GOOGLE_GENAI_API_KEY, CLAUDE_API_KEY, REQUEST_LIMIT, IMAGE_REQUEST_LIMIT
from logger_config import setup_logger
from clients import get_openai_client, get_google_genai_client, get_claude_client
from utilities import load_user_request_data, check_and_reset_user_count
from commands import (
    handle_ask_command_slash,
    handle_google_command_slash,
    handle_claude_command_slash,
    handle_make_command_slash,
)

logger = setup_logger()

# Create a Discord client for slash commands.
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Initialize API clients
openai_client = get_openai_client(OPENAI_API_KEY)
google_client = get_google_genai_client(GOOGLE_GENAI_API_KEY)
claude_client = get_claude_client(CLAUDE_API_KEY)

# Load persistent user data
user_request_data = load_user_request_data()

def split_message(content: str, limit: int = 2000):
    """Split content into chunks of up to 2000 characters."""
    return [content[i : i + limit] for i in range(0, len(content), limit)]

@client.event
async def on_ready():
    # Sync the slash commands with Discord
    await tree.sync()
    logger.info(f"Logged in as {client.user}")

@tree.command(name="ask_gpt", description="Ask GPT-4o-mini a question")
async def ask(interaction: discord.Interaction, question: str):
    uid = str(interaction.user.id)
    global user_request_data
    user_request_data = check_and_reset_user_count(uid, user_request_data)

    await interaction.response.defer()
    result = await handle_ask_command_slash(question, openai_client, user_request_data, REQUEST_LIMIT, uid)
    # If the result is long, split it and send multiple messages
    if len(result) > 2000:
        for chunk in split_message(result):
            await interaction.followup.send(chunk)
    else:
        await interaction.followup.send(result)

@tree.command(name="ask_google", description="Ask Google GenAI a question")
async def ask_google(interaction: discord.Interaction, question: str):
    uid = str(interaction.user.id)
    global user_request_data
    user_request_data = check_and_reset_user_count(uid, user_request_data)

    await interaction.response.defer()
    result = await handle_google_command_slash(question, google_client, user_request_data, REQUEST_LIMIT, uid)
    if len(result) > 2000:
        for chunk in split_message(result):
            await interaction.followup.send(chunk)
    else:
        await interaction.followup.send(result)

@tree.command(name="ask_claude", description="Ask Claude (as a poet) a question")
async def ask_claude(interaction: discord.Interaction, question: str):
    uid = str(interaction.user.id)
    global user_request_data
    user_request_data = check_and_reset_user_count(uid, user_request_data)

    await interaction.response.defer()
    result = await handle_claude_command_slash(question, claude_client, user_request_data, REQUEST_LIMIT, uid)
    if len(result) > 2000:
        for chunk in split_message(result):
            await interaction.followup.send(chunk)
    else:
        await interaction.followup.send(result)

@tree.command(name="make", description="Generate an image using DALL-E-3")
async def make(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    result = await handle_make_command_slash(prompt, openai_client)
    embed = discord.Embed(title="Your Image")
    embed.set_image(url=result)
    await interaction.followup.send(embed=embed)

client.run(DISCORD_BOT_TOKEN)