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
    handle_prompt_command,
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

# Create a command group for /ask
class AskGroup(app_commands.Group):
    """Group for /ask commands."""
    def __init__(self):
        super().__init__(name="ask", description="Ask various AI models")

ask_group = AskGroup()

@ask_group.command(name="gpt", description="Ask GPT-4o-mini a question")
async def ask_gpt(interaction: discord.Interaction, question: str):
    logger.info(f"User {interaction.user} invoked /ask gpt with question: {question}")
    await handle_prompt_command(
        interaction=interaction,
        prompt=question,
        handler=handle_ask_command_slash,
        client=openai_client,
        description="GPT-4o-mini"
    )

@ask_group.command(name="google", description="Ask Google GenAI a question")
async def ask_google(interaction: discord.Interaction, question: str):
    logger.info(f"User {interaction.user} invoked /ask google with question: {question}")
    await handle_prompt_command(
        interaction=interaction,
        prompt=question,
        handler=handle_google_command_slash,
        client=google_client,
        description="Google GenAI"
    )

@ask_group.command(name="claude", description="Ask Claude (as a poet) a question")
async def ask_claude(interaction: discord.Interaction, question: str):
    logger.info(f"User {interaction.user} invoked /ask claude with question: {question}")
    await handle_prompt_command(
        interaction=interaction,
        prompt=question,
        handler=handle_claude_command_slash,
        client=claude_client,
        description="Claude"
    )

@ask_group.command(name="dall-e", description="Generate an image using DALL-E-3")
async def ask_dalle(interaction: discord.Interaction, prompt: str):
    logger.info(f"User {interaction.user} invoked /ask dall-e with prompt: {prompt}")
    await handle_prompt_command(
        interaction=interaction,
        prompt=prompt,
        handler=handle_make_command_slash,
        client=openai_client,
        description="DALL-E-3"
    )

# Add the group to the command tree
tree.add_command(ask_group)

@tree.command(name="clear_history", description="Clear your conversation history")
async def clear_history(interaction: discord.Interaction):
    logger.info(f"User {interaction.user} invoked /clear_history")
    uid = str(interaction.user.id)
    user_state = bot_state.get_user_state(uid)
    user_state.clear_history()
    logger.info(f"Cleared history for user {interaction.user}")
    await interaction.response.send_message("Your conversation history has been cleared.")

client.run(DISCORD_BOT_TOKEN)