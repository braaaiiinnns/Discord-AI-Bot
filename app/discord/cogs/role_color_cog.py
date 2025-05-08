import discord
from discord import app_commands
from discord.ext import commands
import datetime
import logging
import json
import os
from typing import List, Optional
from config.bot_config import COLOR_CHANGE_ROLE_NAMES, PREMIUM_ROLE_NAMES
from config.storage_config import ROLE_COLOR_CYCLES_FILE, PREMIUM_ROLES_FILE

class RoleColorCog(commands.Cog):
    """Cog for managing role colors with a color picker"""
    
    def __init__(self, bot, role_color_manager, logger):
        self.bot = bot
        self.role_color_manager = role_color_manager
        self.logger = logger
        
        self.role_color_cycles_file = ROLE_COLOR_CYCLES_FILE
        self.premium_roles_file = PREMIUM_ROLES_FILE
        self.role_color_cycles = {}
        
        self.load_color_cycles()
        
        # Create command group
        self.color_group = app_commands.Group(name="color", description="Manage your role color")
        
        # Define commands for the group
        self._define_commands()
    
    def _define_commands(self):
        """Define the commands for the color group"""
        # Set command
        @self.color_group.command(name="set", description="Set your role color to a specific hex value or random")
        @app_commands.describe(
            color="Color in hex format (e.g., #FF5733) or 'random'"
        )
        async def color_set(interaction: discord.Interaction, color: str):
            """Set your role color to a specific hex value or random"""
            # Check premium access first and get the premium role to change
            has_access, premium_role = await self._check_premium_access(interaction)
            if not has_access:
                return
            
            # Process the color
            discord_color = None
            
            if color.lower() == 'random':
                # Generate a random color using the role color manager
                rgb_color = self.role_color_manager.generate_distinct_color(
                    interaction.guild.id,
                    premium_role.id,
                    0,  # Single role, so index is 0
                    1   # Only changing one role
                )
                discord_color = discord.Color.from_rgb(*rgb_color)
                hex_color = '#{:02x}{:02x}{:02x}'.format(*rgb_color)
                r, g, b = rgb_color
            else:
                # Parse hex color
                try:
                    # Remove # if present and convert to RGB
                    color = color.lstrip('#')
                    if len(color) != 6:
                        await interaction.response.send_message(
                            "Invalid color format. Please use hex format (e.g., #FF5733) or 'random'.",
                            ephemeral=True
                        )
                        return
                    
                    # Convert to RGB
                    r = int(color[0:2], 16)
                    g = int(color[2:4], 16)
                    b = int(color[4:6], 16)
                    discord_color = discord.Color.from_rgb(r, g, b)
                    hex_color = f"#{color}"
                except ValueError:
                    await interaction.response.send_message(
                        "Invalid color format. Please use hex format (e.g., #FF5733) or 'random'.",
                        ephemeral=True
                    )
                    return
            
            # Change the role color
            await interaction.response.defer(ephemeral=True)
            
            try:
                await premium_role.edit(color=discord_color)
                
                # Store the new color in the role color manager
                color_key = f"{interaction.guild.id}_{premium_role.id}"
                self.role_color_manager.previous_colors[color_key] = (r, g, b)
                self.role_color_manager.save_previous_colors()
                
                # Create a colored box for preview
                colored_box = "■■■■■■■■■■"
                
                embed = discord.Embed(
                    title="Role Color Changed",
                    description=f"Your role **{premium_role.name}** color has been changed to {hex_color}",
                    color=discord_color
                )
                embed.add_field(name="Color Preview", value=colored_box)
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                self.logger.info(f"User {interaction.user} changed premium role {premium_role.name} color to {hex_color}")
            except Exception as e:
                await interaction.followup.send(
                    f"Error changing role color: {str(e)}",
                    ephemeral=True
                )
                self.logger.error(f"Error changing role color: {e}", exc_info=True)
        
        # Picker command
        @self.color_group.command(name="picker", description="Open a color picker to choose a role color")
        async def color_picker(interaction: discord.Interaction):
            """Display a color picker UI for selecting role colors"""
            # Check premium access first and get the premium role to change
            has_access, premium_role = await self._check_premium_access(interaction)
            if not has_access:
                return
            
            # Create a visual color picker using embeds and a grid of color options
            embed = discord.Embed(
                title="🎨 Role Color Picker",
                description=f"Choose a color for your **{premium_role.name}** role by clicking a button below.",
                color=premium_role.color
            )
            
            # Add instructions
            embed.add_field(
                name="Instructions",
                value=(
                    "1. Click on a color group below\n"
                    "2. Choose a specific shade\n"
                    "3. Or use /color set with a hex code for precise control"
                ),
                inline=False
            )
            
            # Create color picker UI with buttons
            view = ColorPickerView(self, interaction.user, premium_role)
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        # Cycle command
        @self.color_group.command(name="cycle", description="Manage your role color cycle")
        @app_commands.describe(
            action="Action to perform with the color cycle",
            color="Color in hex format (e.g., #FF5733) when adding/removing"
        )
        @app_commands.choices(action=[
            app_commands.Choice(name="add", value="add"),
            app_commands.Choice(name="remove", value="remove"),
            app_commands.Choice(name="list", value="list"),
            app_commands.Choice(name="clear", value="clear")
        ])
        async def color_cycle(
            interaction: discord.Interaction, 
            action: str,
            color: Optional[str] = None
        ):
            """Manage a cycle of colors for your role that will rotate daily"""
            # Check premium access first and get the premium role to change
            has_access, premium_role = await self._check_premium_access(interaction)
            if not has_access:
                return
            
            # Create key for this role
            key = f"{interaction.guild.id}_{premium_role.id}"
            
            # Initialize color cycle for this role if it doesn't exist
            if key not in self.color_cycles:
                self.color_cycles[key] = {
                    "colors": [],
                    "role_name": premium_role.name,
                    "guild_id": interaction.guild.id,
                    "last_updated_by": str(interaction.user.id)
                }
            
            if action == "add" and color:
                # Add a color to the cycle
                try:
                    # Remove # if present and verify format
                    color = color.lstrip('#')
                    if len(color) != 6:
                        await interaction.response.send_message(
                            "Invalid color format. Please use hex format (e.g., #FF5733).",
                            ephemeral=True
                        )
                        return
                    
                    # Convert to RGB to validate
                    r = int(color[0:2], 16)
                    g = int(color[2:4], 16)
                    b = int(color[4:6], 16)
                    
                    # Add to cycle
                    hex_color = f"#{color.lower()}"
                    if hex_color in self.color_cycles[key]["colors"]:
                        await interaction.response.send_message(
                            f"Color {hex_color} is already in your cycle.",
                            ephemeral=True
                        )
                        return
                    
                    self.color_cycles[key]["colors"].append(hex_color)
                    self.color_cycles[key]["last_updated_by"] = str(interaction.user.id)
                    self.save_color_cycles()
                    
                    # Preview color
                    discord_color = discord.Color.from_rgb(r, g, b)
                    colored_box = "■■■■■■■■■■"
                    
                    embed = discord.Embed(
                        title="Color Added to Cycle",
                        description=f"Added {hex_color} to the color cycle for role **{premium_role.name}**",
                        color=discord_color
                    )
                    embed.add_field(name="Color Preview", value=colored_box)
                    embed.add_field(
                        name="Colors in Cycle", 
                        value=str(len(self.color_cycles[key]["colors"])),
                        inline=True
                    )
                    
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    self.logger.info(f"User {interaction.user} added {hex_color} to role {premium_role.name} color cycle")
                
                except ValueError:
                    await interaction.response.send_message(
                        "Invalid color format. Please use hex format (e.g., #FF5733).",
                        ephemeral=True
                    )
                    return
            
            elif action == "remove" and color:
                # Remove a color from the cycle
                hex_color = color.lower()
                if not hex_color.startswith('#'):
                    hex_color = f"#{hex_color}"
                
                if hex_color in self.color_cycles[key]["colors"]:
                    self.color_cycles[key]["colors"].remove(hex_color)
                    self.color_cycles[key]["last_updated_by"] = str(interaction.user.id)
                    self.save_color_cycles()
                    await interaction.response.send_message(
                        f"Removed {hex_color} from the color cycle for role **{premium_role.name}**",
                        ephemeral=True
                    )
                    self.logger.info(f"User {interaction.user} removed {hex_color} from role {premium_role.name} color cycle")
                else:
                    await interaction.response.send_message(
                        f"Color {hex_color} is not in your cycle.",
                        ephemeral=True
                    )
            
            elif action == "list":
                # List the colors in the cycle
                if not self.color_cycles[key]["colors"]:
                    await interaction.response.send_message(
                        f"No colors in the cycle for role **{premium_role.name}**.",
                        ephemeral=True
                    )
                    return
                
                embed = discord.Embed(
                    title=f"Color Cycle for {premium_role.name}",
                    description=f"The following colors will be cycled daily for your role.",
                    color=premium_role.color
                )
                
                # Create a color preview with boxes
                preview = ""
                for hex_color in self.color_cycles[key]["colors"]:
                    preview += f"{hex_color} ■ "
                
                embed.add_field(
                    name=f"Colors ({len(self.color_cycles[key]['colors'])})",
                    value=preview or "No colors set",
                    inline=False
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
            
            elif action == "clear":
                # Clear all colors from the cycle
                self.color_cycles[key]["colors"] = []
                self.color_cycles[key]["last_updated_by"] = str(interaction.user.id)
                self.save_color_cycles()
                await interaction.response.send_message(
                    f"Cleared all colors from the cycle for role **{premium_role.name}**.",
                    ephemeral=True
                )
                self.logger.info(f"User {interaction.user} cleared role {premium_role.name} color cycle")
            
            else:
                await interaction.response.send_message(
                    "Invalid action. Use add, remove, list, or clear.",
                    ephemeral=True
                )
        
        # Store the command functions
        self.color_set = color_set
        self.color_picker = color_picker
        self.color_cycle = color_cycle
    
    def load_color_cycles(self):
        """Load saved color cycles from file"""
        try:
            if os.path.exists(self.role_color_cycles_file):
                with open(self.role_color_cycles_file, "r") as f:
                    self.color_cycles = json.load(f)
                self.logger.info(f"Loaded color cycles from {self.role_color_cycles_file}")
            else:
                self.color_cycles = {}
                # Ensure directory exists
                os.makedirs(os.path.dirname(self.role_color_cycles_file), exist_ok=True)
                self.save_color_cycles()
        except Exception as e:
            self.logger.error(f"Error loading color cycles: {e}", exc_info=True)
            self.color_cycles = {}
    
    def save_color_cycles(self):
        """Save color cycles to file"""
        try:
            with open(self.role_color_cycles_file, "w") as f:
                json.dump(self.color_cycles, f)
            self.logger.info(f"Saved color cycles to {self.role_color_cycles_file}")
        except Exception as e:
            self.logger.error(f"Error saving color cycles: {e}", exc_info=True)
    
    def _load_premium_roles(self):
        """Load premium roles from file"""
        if not os.path.exists(self.premium_roles_file):
            return {}
        try:
            with open(self.premium_roles_file, "r") as file:
                return json.load(file)
        except Exception as e:
            self.logger.error(f"Error loading premium roles: {e}", exc_info=True)
            return {}

    async def _check_premium_access(self, interaction: discord.Interaction) -> tuple[bool, discord.Role]:
        """
        Check if the user has access to premium color commands
        Returns (has_access, premium_role) where premium_role is the role to change 
        or None if user has no premium roles
        """
        # Get user's roles
        user_roles = interaction.user.roles
        
        # Load premium roles from file
        saved_premium_roles = self._load_premium_roles()
        
        # Enhanced debugging
        self.logger.info(f"Checking premium access for user {interaction.user.name} (ID: {interaction.user.id})")
        self.logger.info(f"User has roles: {', '.join([role.name for role in user_roles])}")
        self.logger.info(f"Loaded premium roles from file: {saved_premium_roles}")
        self.logger.info(f"PREMIUM_ROLE_NAMES from config: {PREMIUM_ROLE_NAMES}")
        
        # Check if user has a premium role
        has_premium = False
        premium_role = None
        
        # First check against the saved premium roles
        for role in user_roles:
            role_id = str(role.id)
            if role_id in saved_premium_roles:
                has_premium = True
                premium_role = role
                self.logger.info(f"Found premium role match by ID: {role.name} (ID: {role_id})")
                break
        
        # If not found, fallback to checking names against PREMIUM_ROLE_NAMES constant
        if not has_premium:
            for role in user_roles:
                # Trim whitespace for more lenient matching
                role_name_trimmed = role.name.strip()
                for premium_name in PREMIUM_ROLE_NAMES:
                    premium_name_trimmed = premium_name.strip()
                    if role_name_trimmed.lower() == premium_name_trimmed.lower():
                        has_premium = True
                        premium_role = role
                        self.logger.info(f"Found premium role match by name: {role.name} matched with {premium_name}")
                        break
                if has_premium:
                    break
        
        # If user doesn't have premium, send an error message
        if not has_premium:
            embed = discord.Embed(
                title="Premium Feature",
                description="The color command is a premium feature.",
                color=discord.Color.gold()
            )
            embed.add_field(
                name="How to Access",
                value=f"You need one of these roles to use this command: {', '.join(PREMIUM_ROLE_NAMES)}",
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            self.logger.info(f"User {interaction.user} attempted to use premium color command without access")
            return False, None
            
        self.logger.info(f"User {interaction.user} accessed premium color command with role: {premium_role.name}")
        return True, premium_role
    
    async def update_role_color_from_cycle(self):
        """Daily task to update role colors based on cycles"""
        self.logger.info("Running daily role color cycle update")
        
        for key, cycle_data in self.color_cycles.items():
            if not cycle_data["colors"]:
                continue
            
            try:
                guild_id = cycle_data["guild_id"]
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue
                
                # Find the role
                role = None
                for r in guild.roles:
                    if r.name == cycle_data["role_name"]:
                        role = r
                        break
                
                if not role:
                    continue
                
                # Select next color in cycle
                # We'll use the current day of the year to determine the color
                # This ensures everyone sees the same color on the same day
                day_of_year = datetime.datetime.now().timetuple().tm_yday
                color_index = day_of_year % len(cycle_data["colors"])
                hex_color = cycle_data["colors"][color_index]
                
                # Convert to RGB
                color = hex_color.lstrip('#')
                r = int(color[0:2], 16)
                g = int(color[2:4], 16)
                b = int(color[4:6], 16)
                discord_color = discord.Color.from_rgb(r, g, b)
                
                # Update the role
                await role.edit(color=discord_color)
                self.logger.info(f"Updated role {role.name} color to {hex_color} from cycle")
                
                # Store in role color manager
                color_key = f"{guild_id}_{role.id}"
                self.role_color_manager.previous_colors[color_key] = (r, g, b)
                self.role_color_manager.save_previous_colors()
                
            except Exception as e:
                self.logger.error(f"Error updating role color from cycle: {e}", exc_info=True)
    
    async def cog_load(self):
        """Register the command group with the bot when the cog is loaded"""
        # Add the group to the command tree
        self.bot.tree.add_command(self.color_group)
        self.logger.info("Color command group registered")

# Color picker UI
class ColorPickerView(discord.ui.View):
    def __init__(self, cog, user, role):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog
        self.user = user
        self.role = role
        self.add_color_buttons()
    
    def add_color_buttons(self):
        # Add color category buttons
        self.add_item(ColorButton("Red", discord.ButtonStyle.danger, "FF0000"))
        self.add_item(ColorButton("Green", discord.ButtonStyle.success, "00FF00"))
        self.add_item(ColorButton("Blue", discord.ButtonStyle.primary, "0000FF"))
        self.add_item(ColorButton("Yellow", discord.ButtonStyle.secondary, "FFFF00"))
        self.add_item(ColorButton("Purple", discord.ButtonStyle.secondary, "800080"))
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This color picker is not for you.", ephemeral=True)
            return False
        return True

class ColorButton(discord.ui.Button):
    def __init__(self, color_name, style, color_hex):
        super().__init__(
            style=style,
            label=color_name,
            custom_id=f"color_{color_hex}"
        )
        self.color_name = color_name
        self.color_hex = color_hex
    
    async def callback(self, interaction: discord.Interaction):
        # Show color shades for this color family
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"🎨 {self.color_name} Shades",
                description=f"Select a shade of {self.color_name.lower()} for your role.",
                color=discord.Color.from_str(f"#{self.color_hex}")
            ),
            view=ColorShadesView(self.view.cog, self.view.user, self.view.role, self.color_name)
        )

class ColorShadesView(discord.ui.View):
    def __init__(self, cog, user, role, color_family):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog
        self.user = user
        self.role = role
        self.color_family = color_family
        self.add_shade_buttons()
    
    def add_shade_buttons(self):
        if self.color_family == "Red":
            shades = [
                ("Light Red", "FF6666"),
                ("Red", "FF0000"),
                ("Dark Red", "990000"),
                ("Burgundy", "800020"),
                ("Crimson", "DC143C")
            ]
        elif self.color_family == "Green":
            shades = [
                ("Light Green", "90EE90"),
                ("Green", "00FF00"),
                ("Dark Green", "006400"),
                ("Emerald", "50C878"),
                ("Lime", "32CD32")
            ]
        elif self.color_family == "Blue":
            shades = [
                ("Light Blue", "ADD8E6"),
                ("Blue", "0000FF"),
                ("Dark Blue", "00008B"),
                ("Navy", "000080"),
                ("Teal", "008080")
            ]
        elif self.color_family == "Yellow":
            shades = [
                ("Light Yellow", "FFFFE0"),
                ("Yellow", "FFFF00"),
                ("Gold", "FFD700"),
                ("Orange", "FFA500"),
                ("Amber", "FFBF00")
            ]
        elif self.color_family == "Purple":
            shades = [
                ("Lavender", "E6E6FA"),
                ("Light Purple", "BA55D3"),
                ("Purple", "800080"),
                ("Dark Purple", "4B0082"),
                ("Violet", "8F00FF")
            ]
        else:
            shades = []
        
        # Add buttons for each shade
        for name, hex_code in shades:
            self.add_item(ShadeButton(name, hex_code))
        
        # Add a back button
        self.add_item(BackButton())
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This color picker is not for you.", ephemeral=True)
            return False
        return True

class ShadeButton(discord.ui.Button):
    def __init__(self, shade_name, hex_code):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=shade_name,
            custom_id=f"shade_{hex_code}"
        )
        self.shade_name = shade_name
        self.hex_code = hex_code
    
    async def callback(self, interaction: discord.Interaction):
        cog = self.view.cog
        role = self.view.role
        
        # Convert hex to Discord color
        r = int(self.hex_code[0:2], 16)
        g = int(self.hex_code[2:4], 16)
        b = int(self.hex_code[4:6], 16)
        discord_color = discord.Color.from_rgb(r, g, b)
        
        try:
            # Update the role color
            await role.edit(color=discord_color)
            
            # Store the new color in the role color manager
            color_key = f"{interaction.guild.id}_{role.id}"
            cog.role_color_manager.previous_colors[color_key] = (r, g, b)
            cog.role_color_manager.save_previous_colors()
            
            # Show confirmation
            colored_box = "■■■■■■■■■■"
            
            embed = discord.Embed(
                title="Role Color Changed",
                description=f"Your role **{role.name}** color has been changed to #{self.hex_code}",
                color=discord_color
            )
            embed.add_field(name="Color Preview", value=colored_box)
            
            await interaction.response.edit_message(
                embed=embed,
                view=None  # Remove the buttons
            )
            cog.logger.info(f"User {interaction.user} changed role {role.name} color to #{self.hex_code} using picker")
            
        except Exception as e:
            # Show error message
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="Error",
                    description=f"Could not change role color: {str(e)}",
                    color=discord.Color.red()
                ),
                view=None
            )
            cog.logger.error(f"Error changing role color: {e}", exc_info=True)

class BackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="Back to Color Families",
            custom_id="back_to_families"
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Go back to main color picker
        embed = discord.Embed(
            title="🎨 Role Color Picker",
            description=f"Choose a color for your **{self.view.role.name}** role by clicking a button below.",
            color=self.view.role.color
        )
        
        embed.add_field(
            name="Instructions",
            value=(
                "1. Click on a color group below\n"
                "2. Choose a specific shade\n"
                "3. Or use /color set with a hex code for precise control"
            ),
            inline=False
        )
        
        await interaction.response.edit_message(
            embed=embed,
            view=ColorPickerView(self.view.cog, self.view.user, self.view.role)
        )