import discord
from discord import app_commands
from discord.ext import commands

class UserStateCog(commands.Cog):
    """Cog for user state and history management"""
    
    def __init__(self, bot, bot_state, logger):
        self.bot = bot
        self.bot_state = bot_state
        self.logger = logger
    
    @app_commands.command(name="clear_history", description="Clear your conversation history")
    async def clear_history(self, interaction: discord.Interaction):
        """Clear a user's conversation history"""
        self.logger.info(f"User {interaction.user} invoked /clear_history")
        uid = str(interaction.user.id)
        user_state = self.bot_state.get_user_state(uid)
        user_state.clear_history()
        self.logger.info(f"Cleared history for user {interaction.user}")
        await interaction.response.send_message("Your conversation history has been cleared.")