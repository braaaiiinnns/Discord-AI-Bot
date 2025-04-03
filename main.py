import discord
from discord import app_commands
import logging
from config import DISCORD_BOT_TOKEN, REQUEST_LIMIT, OPENAI_API_KEY, GOOGLE_GENAI_API_KEY, CLAUDE_API_KEY
from logger_config import setup_logger
from clients import get_openai_client, get_google_genai_client, get_claude_client
from utilities import load_user_request_data, check_and_reset_user_count, compose_text_response, split_message
from state import BotState
from commands import (
    handle_ask_command_slash,
    handle_google_command_slash,
    handle_claude_command_slash,
    handle_make_command_slash,
)

logger = setup_logger()

# Create a Discord client for slash commands.
intents = discord.Intents.all()  # Adjust as needed.
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Initialize API clients.
openai_client = get_openai_client(OPENAI_API_KEY)
google_client = get_google_genai_client(GOOGLE_GENAI_API_KEY)
claude_client = get_claude_client(CLAUDE_API_KEY)

# Load persistent user data.
user_request_data = load_user_request_data()
bot_state = BotState(timeout=3600)

@client.event
async def on_ready():
    # Sync the command tree
    await tree.sync()
    logger.info(f"Logged in as {client.user}")
    
    # Debugging: Log registered commands
    logger.info("Registered commands:")
    for command in tree.get_commands():
        logger.info(f"- {command.name}")

    # Remove old commands (if necessary)
    guild = discord.Object(id=discord.Interaction.guild_id)  # Replace with your guild ID if testing in a specific server
    await tree.clear_commands(guild=guild)

# Create a command group for /ask
class AskGroup(app_commands.Group):
    """Group for /ask commands."""
    def __init__(self):
        super().__init__(name="ask", description="Ask various AI models")

ask_group = AskGroup()

@ask_group.command(name="gpt", description="Ask GPT-4o-mini a question")
async def ask_gpt(interaction: discord.Interaction, question: str):
    uid = str(interaction.user.id)
    global user_request_data
    user_request_data = check_and_reset_user_count(uid, user_request_data)
    
    await interaction.response.defer()
    try:
        result = await handle_ask_command_slash(question, openai_client, user_request_data, REQUEST_LIMIT, uid)
        full_response = compose_text_response(question, result)
        if len(full_response) > 2000:
            for chunk in split_message(full_response):
                await interaction.followup.send(chunk)
        else:
            await interaction.followup.send(full_response)
    except Exception as e:
        logger.error(f"Error in /ask gpt command: {e}")
        await interaction.followup.send("An error occurred while processing your request. Please try again later.")

@ask_group.command(name="google", description="Ask Google GenAI a question")
async def ask_google(interaction: discord.Interaction, question: str):
    uid = str(interaction.user.id)
    global user_request_data
    user_request_data = check_and_reset_user_count(uid, user_request_data)
    
    await interaction.response.defer()
    try:
        result = await handle_google_command_slash(question, google_client, user_request_data, REQUEST_LIMIT, uid)
        full_response = compose_text_response(question, result)
        if len(full_response) > 2000:
            for chunk in split_message(full_response):
                await interaction.followup.send(chunk)
        else:
            await interaction.followup.send(full_response)
    except Exception as e:
        logger.error(f"Error in /ask google command: {e}")
        await interaction.followup.send("An error occurred while processing your request. Please try again later.")

@ask_group.command(name="claude", description="Ask Claude (as a poet) a question")
async def ask_claude(interaction: discord.Interaction, question: str):
    uid = str(interaction.user.id)
    global user_request_data
    user_request_data = check_and_reset_user_count(uid, user_request_data)
    
    await interaction.response.defer()
    try:
        result = await handle_claude_command_slash(question, claude_client, user_request_data, REQUEST_LIMIT, uid)
        full_response = compose_text_response(question, result)
        if len(full_response) > 2000:
            for chunk in split_message(full_response):
                await interaction.followup.send(chunk)
        else:
            await interaction.followup.send(full_response)
    except Exception as e:
        logger.error(f"Error in /ask claude command: {e}")
        await interaction.followup.send("An error occurred while processing your request. Please try again later.")

@ask_group.command(name="dall-e", description="Generate an image using DALL-E-3")
async def ask_dalle(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    try:
        image_url = await handle_make_command_slash(prompt, openai_client)
        text_response = f"**Prompt:** {prompt}"
        embed = discord.Embed(title="Your Image", description=text_response)
        embed.set_image(url=image_url)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.error(f"Error in /ask dall-e command: {e}")
        await interaction.followup.send("An error occurred while processing your request. Please try again later.")

# Add the group to the command tree
tree.add_command(ask_group)

@tree.command(name="clear_history", description="Clear your conversation history")
async def clear_history(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    user_state = bot_state.get_user_state(uid)
    user_state.clear_history()
    await interaction.response.send_message("Your conversation history has been cleared.")

client.run(DISCORD_BOT_TOKEN)