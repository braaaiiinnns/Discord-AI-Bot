import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import random
from config.bot_config import PREMIUM_ROLE_NAMES
from config.base import ENCRYPTION_KEY
from config.storage_config import PREMIUM_ROLES_FILE
from utils.ncrypt import encrypt_data, decrypt_data

# Confirmation view for admin actions
class ConfirmView(discord.ui.View):
    """Confirmation view with Yes/No buttons"""
    
    def __init__(self, confirm_callback, cancel_callback=None):
        super().__init__(timeout=60)  # 1 minute timeout
        self.confirm_callback = confirm_callback
        self.cancel_callback = cancel_callback
        
    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.confirm_callback(interaction)
        self.stop()
        
    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.cancel_callback:
            await self.cancel_callback(interaction)
        else:
            await interaction.response.send_message("Action cancelled.", ephemeral=True)
        self.stop()

class PremiumRolesCog(commands.Cog):
    """Cog for managing premium roles"""
    
    def __init__(self, bot, logger):
        self.bot = bot
        self.logger = logger
        
        # Add premium roles storage
        self.premium_roles_file = PREMIUM_ROLES_FILE
        self.premium_roles = self._load_premium_roles()
        
        # Create the premium command group
        self.premium_group = app_commands.Group(name="premium", description="Premium role management commands")
        
        # Register commands
        self._register_commands()
    
    def _load_premium_roles(self):
        """Load premium roles from file"""
        if not os.path.exists(self.premium_roles_file):
            return {}
        with open(self.premium_roles_file, "r") as file:
            return json.load(file)
    
    def _save_premium_roles(self):
        """Save premium roles to file"""
        with open(self.premium_roles_file, "w") as file:
            json.dump(self.premium_roles, file, indent=4)
    
    def _register_commands(self):
        """Register commands for the cog using the premium command group"""
        
        # Command to add a premium role
        @self.premium_group.command(name="add_role", description="Add a premium role")
        @app_commands.describe(role="Role to add")
        async def add_premium_role(interaction: discord.Interaction, role: discord.Role):
            """Add a premium role"""
            if role.name in PREMIUM_ROLE_NAMES:
                self.premium_roles[str(role.id)] = role.name
                self._save_premium_roles()
                await interaction.response.send_message(f"Role {role.name} added as premium role.", ephemeral=True)
                self.logger.info(f"User {interaction.user} added premium role: {role.name}")
            else:
                await interaction.response.send_message(f"Role {role.name} is not a valid premium role.", ephemeral=True)
        
        # Command to remove a premium role
        @self.premium_group.command(name="remove_role", description="Remove a premium role")
        @app_commands.describe(role="Role to remove")
        async def remove_premium_role(interaction: discord.Interaction, role: discord.Role):
            """Remove a premium role"""
            role_id = str(role.id)
            if role_id in self.premium_roles:
                del self.premium_roles[role_id]
                self._save_premium_roles()
                await interaction.response.send_message(f"Role {role.name} removed from premium roles.", ephemeral=True)
                self.logger.info(f"User {interaction.user} removed premium role: {role.name}")
            else:
                await interaction.response.send_message(f"Role {role.name} is not a premium role.", ephemeral=True)
        
        # Command to list all premium roles
        @self.premium_group.command(name="list_roles", description="List all premium roles")
        async def list_premium_roles(interaction: discord.Interaction):
            """List all premium roles"""
            if self.premium_roles:
                embed = discord.Embed(
                    title="Premium Roles",
                    description="These roles have access to premium features",
                    color=discord.Color.gold()
                )
                
                for role_id, role_name in self.premium_roles.items():
                    embed.add_field(name=role_name, value=f"ID: {role_id}", inline=False)
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                self.logger.info(f"User {interaction.user} listed premium roles")
            else:
                await interaction.response.send_message("No premium roles found.", ephemeral=True)
    
    async def cog_load(self):
        """Register the premium command group with the bot when the cog is loaded"""
        self.bot.tree.add_command(self.premium_group)
        self.logger.info("Premium command group registered")

async def setup(bot):
    """Setup function for the cog"""
    logger = bot.get_logger("PremiumRolesCog")
    await bot.add_cog(PremiumRolesCog(bot, logger))