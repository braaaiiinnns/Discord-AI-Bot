import discord
from discord import app_commands
import logging
from config import DISCORD_BOT_TOKEN, OPENAI_API_KEY, GOOGLE_GENAI_API_KEY, CLAUDE_API_KEY, REQUEST_LIMIT, IMAGE_REQUEST_LIMIT
from logger_config import setup_logger
from clients import get_openai_client, get_google_genai_client, get_claude_client
from utilities import load_user_request_data, check_and_reset_user_count, compose_text_response
from commands import (
    handle_ask_command_slash,
    handle_google_command_slash,
    handle_claude_command_slash,
    handle_make_command_slash,
)

logger = setup_logger()

# Create a Discord client for slash commands.
intents = discord.Intents.all()  # Change this only if your bot needs additional permissions.
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Initialize API clients.
openai_client = get_openai_client(OPENAI_API_KEY)
google_client = get_google_genai_client(GOOGLE_GENAI_API_KEY)
claude_client = get_claude_client(CLAUDE_API_KEY)

# Encapsulate user_request_data in a class to avoid global variables.
class BotState:
    def __init__(self):
        self.user_request_data = load_user_request_data()

bot_state = BotState()

def split_message(content: str, limit: int = 2000):
    """Split content into chunks of up to 2000 characters."""
    if len(content) <= limit:
        return [content]
    return [content[i : i + limit] for i in range(0, len(content), limit)]

@client.event
async def on_ready():
    # Sync the slash commands with Discord.
    await tree.sync()
    logger.info(f"Logged in as {client.user}")

@tree.command(name="ask_gpt", description="Ask GPT-4o-mini a question")
async def ask(interaction: discord.Interaction, question: str):
    uid = str(interaction.user.id)
    bot_state.user_request_data = check_and_reset_user_count(uid, bot_state.user_request_data)
    
    await interaction.response.defer()
    try:
        result = await handle_ask_command_slash(question, openai_client, bot_state.user_request_data, REQUEST_LIMIT, uid)
        # Compose a full response including the question and answer.
        full_response = compose_text_response(question, result)
        if len(full_response) > 2000:
            for chunk in split_message(full_response):
                await interaction.followup.send(chunk)
        else:
            await interaction.followup.send(full_response)
    except Exception as e:
        logger.error(f"Error in /ask command: {e}")
        await interaction.followup.send("An error occurred while processing your request. Please try again later.")

@tree.command(name="ask_google", description="Ask Google GenAI a question")
async def ask_google(interaction: discord.Interaction, question: str):
    uid = str(interaction.user.id)
    bot_state.user_request_data = check_and_reset_user_count(uid, bot_state.user_request_data)
    
    await interaction.response.defer()
    try:
        result = await handle_google_command_slash(question, google_client, bot_state.user_request_data, REQUEST_LIMIT, uid)
        full_response = compose_text_response(question, result)
        if len(full_response) > 2000:
            for chunk in split_message(full_response):
                await interaction.followup.send(chunk)
        else:
            await interaction.followup.send(full_response)
    except Exception as e:
        logger.error(f"Error in /ask_google command: {e}")
        await interaction.followup.send("An error occurred while processing your request. Please try again later.")

@tree.command(name="ask_claude", description="Ask Claude (as a poet) a question")
async def ask_claude(interaction: discord.Interaction, question: str):
    uid = str(interaction.user.id)
    bot_state.user_request_data = check_and_reset_user_count(uid, bot_state.user_request_data)
    
    await interaction.response.defer()
    try:
        result = await handle_claude_command_slash(question, claude_client, bot_state.user_request_data, REQUEST_LIMIT, uid)
        full_response = compose_text_response(question, result)
        if len(full_response) > 2000:
            for chunk in split_message(full_response):
                await interaction.followup.send(chunk)
        else:
            await interaction.followup.send(full_response)
    except Exception as e:
        logger.error(f"Error in /ask_claude command: {e}")
        await interaction.followup.send("An error occurred while processing your request. Please try again later.")

@tree.command(name="make", description="Generate an image using DALL-E-3")
async def make(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    try:
        result = await handle_make_command_slash(prompt, openai_client)
        # For image commands, include the prompt text along with the embed.
        text_response = f"**Prompt:** {prompt}"
        embed = discord.Embed(title="Your Image", description=text_response)
        embed.set_image(url=result)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.error(f"Error in /make command: {e}")
        await interaction.followup.send("An error occurred while processing your request. Please try again later.")

client.run(DISCORD_BOT_TOKEN)