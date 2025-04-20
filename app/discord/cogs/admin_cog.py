"""
Cog for administrative commands.
"""
import discord
from discord.ext import commands
from discord import app_commands
import logging

class AdminCog(commands.Cog):
    """Cog containing administrative commands for the bot."""
    def __init__(self, bot_instance):
        self.bot_instance = bot_instance
        self.logger = bot_instance.logger # Use the bot's logger instance

    @app_commands.command(name="toggle_debug", description="Toggle debug logging on or off.")
    @app_commands.checks.has_permissions(administrator=True) # Only administrators can use this
    @app_commands.describe(enable="Set to True to enable debug logging, False to disable.")
    async def toggle_debug(self, interaction: discord.Interaction, enable: bool):
        """Toggles the debug logging level for the bot."""
        self.logger.debug(f"toggle_debug command invoked by {interaction.user} with enable={enable}")
        try:
            self.bot_instance.toggle_debug_logging(enable)
            status = "enabled" if enable else "disabled"
            await interaction.response.send_message(f"Debug logging has been {status}.", ephemeral=True)
            self.logger.info(f"Debug logging toggled to {status} by {interaction.user}.")
        except Exception as e:
            self.logger.error(f"Error toggling debug logging: {e}", exc_info=True)
            await interaction.response.send_message("An error occurred while toggling debug logging.", ephemeral=True)

    @toggle_debug.error
    async def toggle_debug_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Error handler for the toggle_debug command."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            self.logger.warning(f"User {interaction.user} attempted to use toggle_debug without permissions.")
        else:
            await interaction.response.send_message("An unexpected error occurred.", ephemeral=True)
            self.logger.error(f"Unexpected error in toggle_debug command: {error}", exc_info=True)

async def setup(bot):
    # We need the main bot instance to access the toggle_debug_logging method
    # Assuming the bot instance is passed during setup or accessible globally
    # This requires modification in how the bot is structured or cogs are loaded
    # For now, let's assume the main bot instance is accessible via bot.bot_instance
    # This needs adjustment based on the actual bot structure in main.py or app/main.py
    if hasattr(bot, 'bot_instance'):
        await bot.add_cog(AdminCog(bot.bot_instance))
        bot.bot_instance.logger.debug("AdminCog loaded.") # Use bot_instance's logger
    else:
        # Fallback or error logging if bot_instance is not found
        # This indicates a structural issue that needs resolving
        logging.getLogger('discord_bot').error("Could not load AdminCog: bot_instance not found on the bot object.")

# Note: The setup function needs access to the DiscordBot instance (self.bot_instance in the cog).
# This might require passing the DiscordBot instance when loading the cog in bot.py or main.py.
# The current setup assumes the main bot object (passed as 'bot' to setup) has an attribute 'bot_instance'
# which refers to the DiscordBot class instance. This needs verification/adjustment.
