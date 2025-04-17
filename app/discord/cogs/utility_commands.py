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

class UtilityCogCommands(commands.Cog):
    """Cog for utility commands"""
    
    def __init__(self, bot, bot_state, logger):
        self.bot = bot
        self.bot_state = bot_state
        self.logger = logger
        self.openai_client = None
        
        # Add premium roles storage
        self.premium_roles_file = "data/files/premium_roles.json"
        self.premium_roles = self._load_premium_roles()
        
        # Register commands
        self._register_commands()
    
    def _register_commands(self):
        """Register all commands in this cog"""
        # Create the premium role group
        self.premium_group = app_commands.Group(
            name="premium", 
            description="Manage premium features and roles",
            default_permissions=discord.Permissions(administrator=True)
        )
        
        # Create the role subgroup
        self.role_group = app_commands.Group(
            name="role",
            description="Manage premium roles",
            parent=self.premium_group
        )
        
        # Add commands to role group using decorator approach
        @self.role_group.command(name="add", description="Create a new premium role")
        async def role_add_cmd(interaction: discord.Interaction, name: str, color: str = None, user: discord.User = None):
            await self.premium_role_add(interaction, name, color, user)
            
        @self.role_group.command(name="remove", description="Remove a premium role")
        async def role_remove_cmd(interaction: discord.Interaction, name: str):
            await self.premium_role_remove(interaction, name)
            
        @self.role_group.command(name="list", description="List all premium roles")
        async def role_list_cmd(interaction: discord.Interaction):
            await self.premium_role_list(interaction)
            
        @self.role_group.command(name="update", description="Update a premium role's properties")
        async def role_update_cmd(interaction: discord.Interaction, name: str, color: str = None, new_name: str = None):
            await self.premium_role_update(interaction, name, color, new_name)
            
        # Add the command group to the bot's command tree
        self.bot.tree.add_command(self.premium_group)
    
    def _load_premium_roles(self):
        """Load premium roles from encrypted file"""
        try:
            if os.path.exists(self.premium_roles_file):
                with open(self.premium_roles_file, "r") as f:
                    encrypted_data = f.read()
                    
                # Use the bot's encryption key as the "user_id" for the encryption functions
                premium_roles = decrypt_data(ENCRYPTION_KEY, encrypted_data)
                self.logger.info(f"Loaded premium roles configuration from {self.premium_roles_file}")
                return premium_roles
            else:
                # Initialize with defaults from config
                default_roles = {}
                
                # We'll initialize with empty dict and populate after bot is ready
                self._save_premium_roles(default_roles)
                return default_roles
                
        except Exception as e:
            self.logger.error(f"Error loading premium roles: {e}", exc_info=True)
            return {}
    
    def _save_premium_roles(self, premium_roles):
        """Save premium roles to encrypted file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.premium_roles_file), exist_ok=True)
            
            # Encrypt the data
            encrypted_data = encrypt_data(ENCRYPTION_KEY, premium_roles)
            
            # Save to file
            with open(self.premium_roles_file, "w") as f:
                f.write(encrypted_data)
                
            self.logger.info(f"Saved premium roles to {self.premium_roles_file}")
            
            # Update global premium roles in memory for compatibility with existing code
            import config.config
            all_premium_roles = set()
            for guild_id, roles in premium_roles.items():
                all_premium_roles.update(roles)
            
            if all_premium_roles:
                config.config.PREMIUM_ROLE_NAMES = list(all_premium_roles)
                
            return True
        except Exception as e:
            self.logger.error(f"Error saving premium roles: {e}", exc_info=True)
            return False
    
    def _parse_color(self, color_str=None):
        """Parse a color string into a Discord color object"""
        if not color_str:
            # Generate a random attractive color if none provided
            r = random.randint(50, 200)
            g = random.randint(50, 200)
            b = random.randint(50, 200)
            return discord.Color.from_rgb(r, g, b)
        
        try:
            # Handle hex colors with or without #
            color_str = color_str.lstrip('#')
            if len(color_str) != 6:
                raise ValueError("Invalid color format")
            
            r = int(color_str[0:2], 16)
            g = int(color_str[2:4], 16)
            b = int(color_str[4:6], 16)
            return discord.Color.from_rgb(r, g, b)
        except ValueError:
            # Return a default color if parsing fails
            return discord.Color.blurple()
    
    async def premium_role_add(self, interaction: discord.Interaction, name: str, color: str = None, user: discord.User = None):
        """Create a new premium role"""
        await interaction.response.defer(ephemeral=True)
        
        guild_id = str(interaction.guild.id)
        
        # Initialize this guild's premium roles if not already done
        if guild_id not in self.premium_roles:
            self.premium_roles[guild_id] = []
        
        # Check if role already exists
        existing_role = discord.utils.get(interaction.guild.roles, name=name)
        if existing_role:
            # Role exists, ask if user wants to mark it as premium
            confirmation = await self._confirm_action(
                interaction,
                f"Role '{name}' already exists. Do you want to mark it as premium?"
            )
            
            if not confirmation:
                return
            
            # Mark as premium and update the color if requested
            if color:
                discord_color = self._parse_color(color)
                try:
                    await existing_role.edit(color=discord_color)
                    result_msg = f"Updated role '{name}' color and marked it as premium."
                except discord.Forbidden:
                    result_msg = f"Marked role '{name}' as premium but couldn't update color (missing permissions)."
            else:
                result_msg = f"Marked existing role '{name}' as premium."
                
            # Add to premium roles if not already there
            if name not in self.premium_roles[guild_id]:
                self.premium_roles[guild_id].append(name)
                self._save_premium_roles(self.premium_roles)
                
            # Assign the role to the user if specified
            if user and existing_role:
                member = interaction.guild.get_member(user.id)
                if member:
                    try:
                        await member.add_roles(existing_role, reason=f"Assigned premium role '{name}' by {interaction.user}")
                        result_msg += f" Role was assigned to {user.mention}."
                    except discord.Forbidden:
                        result_msg += f" Couldn't assign role to {user.mention} (missing permissions)."
                    except discord.HTTPException as e:
                        result_msg += f" Couldn't assign role to {user.mention}: Discord API error ({e})."
                else:
                    result_msg += f" Couldn't assign role to {user.display_name} (user not found in server)."
        else:
            # Create new role with specified color
            discord_color = self._parse_color(color)
            
            try:
                # Create the role at a position above the bot's highest role
                bot_member = interaction.guild.get_member(self.bot.user.id)
                position = bot_member.top_role.position - 1 if bot_member.top_role.position > 0 else 0
                
                # Create the role
                new_role = await interaction.guild.create_role(
                    name=name,
                    color=discord_color,
                    reason=f"Premium role created by {interaction.user}"
                )
                
                # Try to set the position (this might fail if the bot's role isn't high enough)
                try:
                    await new_role.edit(position=position)
                except discord.HTTPException:
                    # Ignore position errors, the role is still created
                    pass
                
                # Add to premium roles
                self.premium_roles[guild_id].append(name)
                self._save_premium_roles(self.premium_roles)
                
                hex_color = f"#{color}" if color else f"#{discord_color.value:06x}"
                result_msg = f"Created new premium role '{name}' with color {hex_color}"
                
                # Assign the role to the user if specified
                if user:
                    member = interaction.guild.get_member(user.id)
                    if member:
                        try:
                            await member.add_roles(new_role, reason=f"Assigned premium role '{name}' by {interaction.user}")
                            result_msg += f" and assigned it to {user.mention}"
                        except discord.Forbidden:
                            result_msg += f". Couldn't assign role to {user.mention} (missing permissions)."
                        except discord.HTTPException as e:
                            result_msg += f". Couldn't assign role to {user.mention}: Discord API error ({e})."
                    else:
                        result_msg += f". Couldn't assign role to {user.display_name} (user not found in server)."
                
            except discord.Forbidden:
                result_msg = "Failed to create role: Missing permissions. The bot needs the 'Manage Roles' permission."
            except discord.HTTPException as e:
                result_msg = f"Failed to create role: Discord API error ({e})"
        
        # Send result message
        embed = discord.Embed(
            title="Premium Role Added",
            description=result_msg,
            color=discord_color if 'discord_color' in locals() else discord.Color.green()
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        self.logger.info(f"Admin {interaction.user} {result_msg}")
    
    async def premium_role_remove(self, interaction: discord.Interaction, name: str):
        """Remove a premium role"""
        await interaction.response.defer(ephemeral=True)
        
        guild_id = str(interaction.guild.id)
        
        # Check if this guild has any premium roles
        if guild_id not in self.premium_roles or name not in self.premium_roles[guild_id]:
            await interaction.followup.send(
                f"Role '{name}' is not registered as a premium role.",
                ephemeral=True
            )
            return
        
        # Find the role in Discord
        role = discord.utils.get(interaction.guild.roles, name=name)
        
        # Ask for confirmation
        delete_msg = f"Delete the '{name}' role from Discord" if role else f"Remove '{name}' from premium roles"
        confirmation = await self._confirm_action(
            interaction,
            f"{delete_msg}? This action cannot be undone."
        )
        
        if not confirmation:
            return
        
        # Remove from premium roles list
        self.premium_roles[guild_id].remove(name)
        self._save_premium_roles(self.premium_roles)
        
        # Delete the actual role if it exists
        result_msg = ""
        if role:
            try:
                await role.delete(reason=f"Premium role removed by {interaction.user}")
                result_msg = f"Deleted role '{name}' from Discord and removed from premium roles."
            except discord.Forbidden:
                result_msg = f"Removed '{name}' from premium roles but couldn't delete it (missing permissions)."
            except discord.HTTPException as e:
                result_msg = f"Removed '{name}' from premium roles but couldn't delete it: Discord API error ({e})"
        else:
            result_msg = f"Removed '{name}' from premium roles. The role did not exist in Discord."
        
        # Send result
        embed = discord.Embed(
            title="Premium Role Removed",
            description=result_msg,
            color=discord.Color.red()
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        self.logger.info(f"Admin {interaction.user} {result_msg}")
    
    async def premium_role_list(self, interaction: discord.Interaction):
        """List all premium roles"""
        await interaction.response.defer(ephemeral=True)
        
        guild_id = str(interaction.guild.id)
        
        # Initialize this guild's premium roles if not already done
        if guild_id not in self.premium_roles:
            self.premium_roles[guild_id] = []
            self._save_premium_roles(self.premium_roles)
        
        # Create embed
        embed = discord.Embed(
            title="Premium Roles",
            description="The following roles have premium access:",
            color=discord.Color.gold()
        )
        
        # Add each role to the embed, with a check if it exists in the guild
        if not self.premium_roles[guild_id]:
            embed.add_field(
                name="No Premium Roles",
                value="No premium roles have been configured. Use `/premium role add` to create one.",
                inline=False
            )
        else:
            existing_roles = []
            missing_roles = []
            
            for role_name in self.premium_roles[guild_id]:
                role = discord.utils.get(interaction.guild.roles, name=role_name)
                if role:
                    hex_color = f"#{role.color.value:06x}"
                    existing_roles.append(f"✅ {role.mention} - Color: {hex_color}")
                else:
                    missing_roles.append(f"❌ {role_name} (not found in Discord)")
            
            if existing_roles:
                embed.add_field(name="Active Premium Roles", value="\n".join(existing_roles), inline=False)
            
            if missing_roles:
                embed.add_field(name="Missing Roles", value="\n".join(missing_roles), inline=False)
                embed.add_field(
                    name="Note", 
                    value="Missing roles are defined but don't exist in the server. Use `/premium role add` to create them.",
                    inline=False
                )
        
        # Add instructions
        embed.add_field(
            name="Managing Premium Roles",
            value=(
                "• `/premium role add <name> <user> [color]` - Create a new premium role\n"
                "• `/premium role remove <name>` - Remove a premium role\n"
                "• `/premium role update <name> [color] [new_name]` - Update a role's properties"
            ),
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    async def premium_role_update(self, interaction: discord.Interaction, name: str, color: str = None, new_name: str = None):
        """Update a premium role's properties"""
        await interaction.response.defer(ephemeral=True)
        
        guild_id = str(interaction.guild.id)
        
        # Check if this guild has any premium roles
        if guild_id not in self.premium_roles:
            self.premium_roles[guild_id] = []
        
        # Check if role is premium
        is_premium = name in self.premium_roles[guild_id]
        
        # Find the role in Discord
        role = discord.utils.get(interaction.guild.roles, name=name)
        if not role:
            await interaction.followup.send(
                f"Role '{name}' doesn't exist in this server.",
                ephemeral=True
            )
            return
        
        # Determine changes
        changes = []
        if color:
            discord_color = self._parse_color(color)
            changes.append(f"color to {color}")
        else:
            discord_color = role.color
            
        if new_name:
            changes.append(f"name to '{new_name}'")
        
        if not changes:
            await interaction.followup.send(
                "No changes specified. Please provide a new color or name.",
                ephemeral=True
            )
            return
        
        # Update the role
        try:
            if new_name:
                await role.edit(name=new_name, color=discord_color)
            else:
                await role.edit(color=discord_color)
                
            # Update premium roles list if name changed
            if new_name and is_premium:
                self.premium_roles[guild_id].remove(name)
                self.premium_roles[guild_id].append(new_name)
                self._save_premium_roles(self.premium_roles)
            
            # If not already premium, ask if it should be
            if not is_premium:
                confirmation = await self._confirm_action(
                    interaction,
                    f"Role '{name}' is not registered as a premium role. Add it to premium roles?"
                )
                
                if confirmation:
                    role_name = new_name if new_name else name
                    self.premium_roles[guild_id].append(role_name)
                    self._save_premium_roles(self.premium_roles)
                    result_msg = f"Updated role and added it to premium roles."
                else:
                    result_msg = f"Updated role but did not add it to premium roles."
            else:
                result_msg = f"Updated premium role."
            
            # Send result
            embed = discord.Embed(
                title="Role Updated",
                description=f"{result_msg} Changes: {', '.join(changes)}",
                color=discord_color
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.logger.info(f"Admin {interaction.user} updated role '{name}': {', '.join(changes)}")
            
        except discord.Forbidden:
            await interaction.followup.send(
                "Failed to update role: Missing permissions. The bot needs the 'Manage Roles' permission.",
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"Failed to update role: Discord API error ({e})",
                ephemeral=True
            )
    
    async def _confirm_action(self, interaction, message):
        """Utility method to confirm an action with the user"""
        # Create confirmation buttons
        confirm_view = ConfirmView(timeout=60.0)
        
        # Send confirmation message with buttons
        confirm_msg = await interaction.followup.send(
            message,
            view=confirm_view,
            ephemeral=True
        )
        
        # Wait for confirmation
        await confirm_view.wait()
        
        # Clean up the message by removing buttons
        await confirm_msg.edit(view=None)
        
        return confirm_view.value
    
    def setup_clients(self, openai_client):
        """Setup OpenAI client for image generation"""
        self.openai_client = openai_client
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Called when the bot is ready"""
        # Setup default premium roles for all guilds
        for guild in self.bot.guilds:
            guild_id = str(guild.id)
            if guild_id not in self.premium_roles:
                self.premium_roles[guild_id] = list(PREMIUM_ROLE_NAMES)
        
        # Save the premium roles
        self._save_premium_roles(self.premium_roles)
    
    async def cog_load(self):
        """Register the command group with the bot when the cog is loaded"""
        self.bot.tree.add_command(self.premium_group)
        self.logger.info("Premium command group registered")
    
    @app_commands.command(name="clear_history", description="Clear your conversation history")
    async def clear_history(self, interaction: discord.Interaction):
        """Clear a user's conversation history"""
        self.logger.info(f"User {interaction.user} invoked /clear_history")
        uid = str(interaction.user.id)
        user_state = self.bot_state.get_user_state(uid)
        user_state.clear_history()
        self.logger.info(f"Cleared history for user {interaction.user}")
        await interaction.response.send_message("Your conversation history has been cleared.")
    
    @app_commands.command(name="make", description="Generate an image using DALL-E 3")
    async def make_image(self, interaction: discord.Interaction, prompt: str):
        """Generate an image using DALL-E 3"""
        self.logger.info(f"User {interaction.user} requested image generation: {prompt}")
        await interaction.response.defer()
        
        try:
            # Generate the image using OpenAI's DALL-E 3
            self.logger.info("Generating image using DALL-E 3...")
            response = self.openai_client.images.generate(
                prompt=prompt,
                n=1,  # Generate one image
                size="1024x1024"  # Specify the image size
            )
            image_url = response.data[0].url
            self.logger.info(f"Image generated successfully")
            
            # Send the image URL to the user
            await interaction.followup.send(f"Here is your generated image:\n{image_url}")
        except Exception as e:
            self.logger.error(f"Error generating image: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while generating the image. Please try again later.")
    
    @app_commands.command(name="dashboard", description="Get the URL to the bot's data dashboard")
    async def get_dashboard(self, interaction: discord.Interaction):
        """Get the URL to access the bot's dashboard"""
        self.logger.info(f"User {interaction.user} requested dashboard URL")
        
        # Check if we can access the dashboard from the client
        dashboard = None
        if hasattr(self.bot, 'dashboard') and self.bot.dashboard and self.bot.dashboard.running:
            dashboard_url = f"http://{self.bot.dashboard.host}:{self.bot.dashboard.port}"
            
            # Respond with the URL (ephemeral message for privacy)
            embed = discord.Embed(
                title="📊 Bot Dashboard",
                description=f"Access the data dashboard at: [Dashboard Link]({dashboard_url})",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="What's in the Dashboard?", 
                value="• Message activity statistics\n• User engagement metrics\n• File storage analytics\n• AI interaction data"
            )
            embed.set_footer(text="Data updates every 60 seconds. Optimized for log(n) access.")
            
            # Make the message ephemeral so only the command user can see it
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            # Dashboard is not available
            await interaction.response.send_message(
                "⚠️ The dashboard is not currently available. Please contact the bot administrator.",
                ephemeral=True
            )
            
    @commands.Cog.listener()
    async def on_message(self, message):
        """
        Event listener example for messages.
        Only responds to "hello bot" to demonstrate cog listeners.
        """
        # Don't respond to bot messages to avoid loops
        if message.author.bot:
            return
            
        # Example of a listener that triggers on specific content
        if "hello bot" in message.content.lower():
            await message.channel.send(f"Hello {message.author.mention}! I'm listening to events in my utility cog.")