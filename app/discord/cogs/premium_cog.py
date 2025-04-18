import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import random
from config.config import PREMIUM_ROLE_NAMES, ENCRYPTION_KEY
from utils.ncrypt import encrypt_data, decrypt_data

# Confirmation view for admin actions
class ConfirmView(discord.ui.View):
    """Confirmation view with Yes/No buttons"""
    def __init__(self, timeout=60):
        super().__init__(timeout=timeout)
        self.value = None
    
    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm button callback"""
        self.value = True
        self.stop()
        await interaction.response.defer()
    
    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel button callback"""
        self.value = False
        self.stop()
        await interaction.response.defer()

class PremiumRolesCog(commands.Cog):
    """Cog for managing premium roles"""
    
    def __init__(self, bot, logger):
        self.bot = bot
        self.logger = logger
        
        # Add premium roles storage
        self.premium_roles_file = "data/files/premium_roles.json"
        self.premium_roles = self._load_premium_roles()
        
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
        """Register commands for the cog"""
        @self.bot.tree.command(name="add_premium_role", description="Add a premium role")
        @app_commands.describe(role="Role to add")
        async def add_premium_role(interaction: discord.Interaction, role: discord.Role):
            """Add a premium role"""
            if role.name in PREMIUM_ROLE_NAMES:
                self.premium_roles[role.id] = role.name
                self._save_premium_roles()
                await interaction.response.send_message(f"Role {role.name} added as premium role.", ephemeral=True)
            else:
                await interaction.response.send_message(f"Role {role.name} is not a valid premium role.", ephemeral=True)
        
        @self.bot.tree.command(name="remove_premium_role", description="Remove a premium role")
        @app_commands.describe(role="Role to remove")
        async def remove_premium_role(interaction: discord.Interaction, role: discord.Role):
            """Remove a premium role"""
            if role.id in self.premium_roles:
                del self.premium_roles[role.id]
                self._save_premium_roles()
                await interaction.response.send_message(f"Role {role.name} removed from premium roles.", ephemeral=True)
            else:
                await interaction.response.send_message(f"Role {role.name} is not a premium role.", ephemeral=True)
        
        @self.bot.tree.command(name="list_premium_roles", description="List all premium roles")
        async def list_premium_roles(interaction: discord.Interaction):
            """List all premium roles"""
            if self.premium_roles:
                roles_list = "\n".join([f"{role_id}: {role_name}" for role_id, role_name in self.premium_roles.items()])
                await interaction.response.send_message(f"Premium roles:\n{roles_list}", ephemeral=True)
            else:
                await interaction.response.send_message("No premium roles found.", ephemeral=True)

async def setup(bot):
    """Setup function for the cog"""
    logger = bot.get_logger("PremiumRolesCog")
    await bot.add_cog(PremiumRolesCog(bot, logger))