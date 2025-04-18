import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import re
import random
from typing import Dict, List, Callable, Optional, Union, Any, Pattern, Literal
import asyncio

class MessageListener:
    """
    Class representing a configurable message listener with customizable triggers and actions.
    """
    def __init__(
        self,
        name: str,
        description: str,
        trigger_type: str,
        trigger_value: Union[str, List[str], Pattern],
        action_type: str,
        action_value: Any,
        cooldown: int = 0,
        chance: float = 1.0,
        enabled: bool = True,
        ignore_case: bool = True,
        require_mention: bool = False,
        allowed_channels: Optional[List[int]] = None,
        disallowed_channels: Optional[List[int]] = None,
        allowed_roles: Optional[List[int]] = None,
        disallowed_roles: Optional[List[int]] = None
    ):
        """
        Initialize a new message listener with custom triggers and actions.
        
        Parameters:
            name (str): Unique name for this listener
            description (str): Description of what this listener does
            trigger_type (str): Type of trigger ('contains', 'exact', 'startswith', 'endswith', 'regex', 'contains_any')
            trigger_value: The value to match against (string, list of strings, or compiled regex pattern)
            action_type (str): Type of action ('reply', 'react', 'dm', 'webhook', 'custom')
            action_value: Value for the action (text response, emoji, etc.)
            cooldown (int): Cooldown in seconds between triggers for the same user
            chance (float): Probability (0.0-1.0) that the action will trigger when conditions are met
            enabled (bool): Whether this listener is active
            ignore_case (bool): Whether to ignore case in string matching
            require_mention (bool): Whether the bot must be mentioned for this to trigger
            allowed_channels (List[int]): List of channel IDs where this listener can trigger (None = all channels)
            disallowed_channels (List[int]): List of channel IDs where this listener cannot trigger
            allowed_roles (List[int]): List of role IDs that users must have for this to trigger (None = all roles)
            disallowed_roles (List[int]): List of role IDs that users must not have for this to trigger
        """
        self.name = name
        self.description = description
        self.trigger_type = trigger_type
        
        # Handle different trigger types
        if trigger_type == 'regex' and isinstance(trigger_value, str):
            self.trigger_value = re.compile(trigger_value, re.IGNORECASE if ignore_case else 0)
        else:
            self.trigger_value = trigger_value
            
        self.action_type = action_type
        self.action_value = action_value
        self.cooldown = cooldown
        self.chance = chance
        self.enabled = enabled
        self.ignore_case = ignore_case
        self.require_mention = require_mention
        self.allowed_channels = allowed_channels or []
        self.disallowed_channels = disallowed_channels or []
        self.allowed_roles = allowed_roles or []
        self.disallowed_roles = disallowed_roles or []
        
        # Tracking user cooldowns
        self.user_cooldowns = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the listener to a dictionary for serialization"""
        # Handle special case of regex pattern
        if self.trigger_type == 'regex' and hasattr(self.trigger_value, 'pattern'):
            trigger_value = self.trigger_value.pattern
        else:
            trigger_value = self.trigger_value
            
        return {
            'name': self.name,
            'description': self.description,
            'trigger_type': self.trigger_type,
            'trigger_value': trigger_value,
            'action_type': self.action_type,
            'action_value': self.action_value,
            'cooldown': self.cooldown,
            'chance': self.chance,
            'enabled': self.enabled,
            'ignore_case': self.ignore_case,
            'require_mention': self.require_mention,
            'allowed_channels': self.allowed_channels,
            'disallowed_channels': self.disallowed_channels,
            'allowed_roles': self.allowed_roles,
            'disallowed_roles': self.disallowed_roles
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MessageListener':
        """Create a MessageListener from a dictionary"""
        return cls(**data)
    
    def check_cooldown(self, user_id: int) -> bool:
        """
        Check if user is on cooldown.
        Returns True if the user can trigger the action (not on cooldown).
        """
        if self.cooldown <= 0:
            return True
            
        current_time = asyncio.get_event_loop().time()
        last_trigger = self.user_cooldowns.get(user_id, 0)
        
        if current_time - last_trigger >= self.cooldown:
            self.user_cooldowns[user_id] = current_time
            return True
        return False
    
    def should_trigger(self, message: discord.Message) -> bool:
        """
        Check if this listener should trigger based on the message and all conditions.
        """
        if not self.enabled:
            return False
            
        # Random chance check
        if random.random() > self.chance:
            return False
            
        # Channel restrictions
        if self.allowed_channels and message.channel.id not in self.allowed_channels:
            return False
        if message.channel.id in self.disallowed_channels:
            return False
            
        # Role restrictions
        if isinstance(message.author, discord.Member):
            user_role_ids = [role.id for role in message.author.roles]
            if self.allowed_roles and not any(role_id in user_role_ids for role_id in self.allowed_roles):
                return False
            if any(role_id in user_role_ids for role_id in self.disallowed_roles):
                return False
                
        # Bot mention requirement
        if self.require_mention and not message.mentions:
            return False
        if self.require_mention and not any(mention.id == message.guild.me.id for mention in message.mentions):
            return False
            
        # Cooldown check
        if not self.check_cooldown(message.author.id):
            return False
            
        # Message content checks based on trigger type
        content = message.content
        if self.ignore_case and isinstance(content, str):
            content = content.lower()
            
        if self.trigger_type == 'contains':
            trigger = self.trigger_value.lower() if self.ignore_case and isinstance(self.trigger_value, str) else self.trigger_value
            return trigger in content
            
        elif self.trigger_type == 'exact':
            trigger = self.trigger_value.lower() if self.ignore_case and isinstance(self.trigger_value, str) else self.trigger_value
            return content == trigger
            
        elif self.trigger_type == 'startswith':
            trigger = self.trigger_value.lower() if self.ignore_case and isinstance(self.trigger_value, str) else self.trigger_value
            return content.startswith(trigger)
            
        elif self.trigger_type == 'endswith':
            trigger = self.trigger_value.lower() if self.ignore_case and isinstance(self.trigger_value, str) else self.trigger_value
            return content.endswith(trigger)
            
        elif self.trigger_type == 'regex':
            return bool(self.trigger_value.search(content))
            
        elif self.trigger_type == 'contains_any':
            triggers = [t.lower() if self.ignore_case and isinstance(t, str) else t for t in self.trigger_value]
            return any(trigger in content for trigger in triggers)
            
        return False

    async def execute_action(self, bot: commands.Bot, message: discord.Message) -> None:
        """
        Execute the action for this listener based on the action type.
        """
        try:
            if self.action_type == 'reply':
                # For reply actions, format the response with variables
                response = self._format_response(self.action_value, message)
                await message.channel.send(response)
                
            elif self.action_type == 'react':
                # For reaction actions, add the emoji as a reaction
                await message.add_reaction(self.action_value)
                
            elif self.action_type == 'dm':
                # For DM actions, send a direct message to the user
                response = self._format_response(self.action_value, message)
                await message.author.send(response)
                
            elif self.action_type == 'webhook':
                # For webhook actions, a bit more complex - only if channel has webhook permissions
                if isinstance(message.channel, discord.TextChannel) and message.channel.permissions_for(message.guild.me).manage_webhooks:
                    webhooks = await message.channel.webhooks()
                    webhook = discord.utils.get(webhooks, name="MessageListener")
                    
                    if webhook is None:
                        webhook = await message.channel.create_webhook(name="MessageListener")
                        
                    # webhook_data should be a dict with 'content', 'username', and 'avatar_url'
                    webhook_data = self.action_value
                    content = self._format_response(webhook_data.get('content', ''), message)
                    
                    await webhook.send(
                        content=content,
                        username=webhook_data.get('username', 'Message Listener'),
                        avatar_url=webhook_data.get('avatar_url', None)
                    )
                    
            # Custom actions would be implemented at the cog level and accessed by name
        except Exception as e:
            print(f"Error executing action for listener {self.name}: {e}")
    
    def _format_response(self, response_template: str, message: discord.Message) -> str:
        """
        Format a response template with variables from the message.
        
        Supported variables:
        - {user} - Username
        - {user.mention} - User mention
        - {user.id} - User ID
        - {channel} - Channel name
        - {guild} - Server name
        - {random.number:min:max} - Random number between min and max
        - {message} - User's message content
        - {message.id} - Message ID
        - {timestamp} - Current timestamp
        - {count:name} - Increment and show a counter with the given name
        """
        if not isinstance(response_template, str):
            return str(response_template)
            
        # Basic replacements
        replacements = {
            '{user}': message.author.display_name,
            '{user.mention}': message.author.mention,
            '{user.id}': str(message.author.id),
            '{channel}': getattr(message.channel, 'name', 'Unknown'),
            '{guild}': getattr(message.guild, 'name', 'Unknown'),
            '{message}': message.content,
            '{message.id}': str(message.id),
            '{timestamp}': discord.utils.format_dt(discord.utils.utcnow())
        }
        
        result = response_template
        for key, value in replacements.items():
            result = result.replace(key, value)
            
        # Handle random numbers
        random_pattern = r'\{random\.number:(\d+):(\d+)\}'
        for match in re.finditer(random_pattern, response_template):
            min_val = int(match.group(1))
            max_val = int(match.group(2))
            random_num = str(random.randint(min_val, max_val))
            result = result.replace(match.group(0), random_num)
            
        return result

# UI Components for configuring listeners
class ListenerModal(discord.ui.Modal):
    """Modal for creating or editing a listener"""
    
    def __init__(self, cog, existing_listener=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cog = cog
        self.existing_listener = existing_listener
        
        # Initialize with existing values if editing
        name_value = ""
        description_value = ""
        trigger_value_text = ""
        action_value_text = ""
        
        if existing_listener:
            name_value = existing_listener.name
            description_value = existing_listener.description
            
            # Convert trigger_value to string
            if existing_listener.trigger_type == 'regex' and hasattr(existing_listener.trigger_value, 'pattern'):
                trigger_value_text = existing_listener.trigger_value.pattern
            elif isinstance(existing_listener.trigger_value, list):
                trigger_value_text = ", ".join(existing_listener.trigger_value)
            else:
                trigger_value_text = str(existing_listener.trigger_value)
                
            # Convert action_value to string
            if existing_listener.action_type == 'webhook' and isinstance(existing_listener.action_value, dict):
                action_value_text = json.dumps(existing_listener.action_value)
            else:
                action_value_text = str(existing_listener.action_value)
        
        # Add form fields
        self.name = discord.ui.TextInput(
            label="Listener Name",
            placeholder="Enter a unique name for this listener",
            default=name_value,
            required=True,
            max_length=32
        )
        self.add_item(self.name)
        
        self.description = discord.ui.TextInput(
            label="Description",
            placeholder="Describe what this listener does",
            default=description_value,
            required=True,
            max_length=100
        )
        self.add_item(self.description)
        
        self.trigger_value = discord.ui.TextInput(
            label="Trigger Value",
            placeholder="Word/phrase to trigger on, or comma-separated list",
            default=trigger_value_text,
            required=True,
            max_length=1000
        )
        self.add_item(self.trigger_value)
        
        self.action_value = discord.ui.TextInput(
            label="Response/Action",
            placeholder="What the bot should say/do when triggered",
            default=action_value_text,
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=2000
        )
        self.add_item(self.action_value)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Process the form submission"""
        # Get values from the form
        name = self.name.value.strip()
        description = self.description.value.strip()
        trigger_value_raw = self.trigger_value.value.strip()
        action_value_raw = self.action_value.value.strip()
        
        # Check if we're in edit mode
        is_edit = self.existing_listener is not None
        
        # If creating new, check for name uniqueness
        if not is_edit and self.cog.get_listener(name):
            await interaction.response.send_message(
                f"Error: A listener named '{name}' already exists. Please choose a different name.",
                ephemeral=True
            )
            return
        
        # Get the current settings view to access the selected types and values
        view = interaction.message.view if is_edit and hasattr(interaction, 'message') else None
        
        # Get trigger and action type from the view or use defaults
        trigger_type = "contains"
        action_type = "reply"
        chance = 1.0
        cooldown = 0
        
        if view:
            # Get the selected dropdown values
            for child in view.children:
                if isinstance(child, discord.ui.Select):
                    if child.placeholder == "Select Trigger Type":
                        trigger_type = child.values[0] if child.values else "contains"
                    elif child.placeholder == "Select Action Type":
                        action_type = child.values[0] if child.values else "reply"
                elif isinstance(child, discord.ui.TextInput):
                    if child.label == "Chance (0.0-1.0)":
                        chance = float(child.value) if child.value else 1.0
                    elif child.label == "Cooldown (seconds)":
                        cooldown = int(child.value) if child.value else 0
        
        # Process trigger value based on type
        if trigger_type == 'contains_any':
            # Split by comma and strip whitespace
            trigger_value = [item.strip() for item in trigger_value_raw.split(",")]
        elif trigger_type == 'regex':
            # Keep as string, will be compiled when the listener is created
            trigger_value = trigger_value_raw
        else:
            # For all other types, use as-is
            trigger_value = trigger_value_raw
        
        # Process action value based on type
        if action_type == 'webhook':
            try:
                # Try to parse as JSON
                action_value = json.loads(action_value_raw)
            except json.JSONDecodeError:
                # If not valid JSON, use as content with default username
                action_value = {
                    "content": action_value_raw,
                    "username": "Message Listener"
                }
        else:
            # For all other types, use as-is
            action_value = action_value_raw
        
        # Create or update the listener
        listener_data = {
            "name": name,
            "description": description,
            "trigger_type": trigger_type,
            "trigger_value": trigger_value,
            "action_type": action_type,
            "action_value": action_value,
            "chance": chance,
            "cooldown": cooldown,
            "enabled": True if not is_edit else self.existing_listener.enabled,
            "ignore_case": True if not is_edit else self.existing_listener.ignore_case,
            "require_mention": False if not is_edit else self.existing_listener.require_mention,
            "allowed_channels": [] if not is_edit else self.existing_listener.allowed_channels,
            "disallowed_channels": [] if not is_edit else self.existing_listener.disallowed_channels,
            "allowed_roles": [] if not is_edit else self.existing_listener.allowed_roles,
            "disallowed_roles": [] if not is_edit else self.existing_listener.disallowed_roles
        }
        
        # Create or update the listener
        if is_edit:
            # For edits, remove the old listener and add the new one with the same name
            self.cog.remove_listener(name)
            self.cog.add_listener(MessageListener.from_dict(listener_data))
            await interaction.response.send_message(
                f"✅ Listener '{name}' has been updated successfully!",
                ephemeral=True
            )
        else:
            # For new listeners, just add it
            result = self.cog.add_listener(MessageListener.from_dict(listener_data))
            if result:
                await interaction.response.send_message(
                    f"✅ Listener '{name}' has been created successfully!",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"Error creating listener. Please try again.",
                    ephemeral=True
                )

class ListenerConfigView(discord.ui.View):
    """View for configuring a message listener with dropdowns and buttons"""
    
    def __init__(self, cog, listener=None):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog
        self.listener = listener
        
        # Add trigger type selector
        trigger_options = [
            discord.SelectOption(
                label="Contains",
                description="Trigger when message contains this text",
                value="contains",
                default=listener.trigger_type == "contains" if listener else True
            ),
            discord.SelectOption(
                label="Exact Match",
                description="Trigger on exact message match",
                value="exact",
                default=listener.trigger_type == "exact" if listener else False
            ),
            discord.SelectOption(
                label="Starts With",
                description="Trigger when message starts with this text",
                value="startswith",
                default=listener.trigger_type == "startswith" if listener else False
            ),
            discord.SelectOption(
                label="Ends With",
                description="Trigger when message ends with this text",
                value="endswith",
                default=listener.trigger_type == "endswith" if listener else False
            ),
            discord.SelectOption(
                label="Regular Expression",
                description="Trigger using regex pattern match",
                value="regex",
                default=listener.trigger_type == "regex" if listener else False
            ),
            discord.SelectOption(
                label="Contains Any",
                description="Trigger if message contains any of the comma-separated values",
                value="contains_any",
                default=listener.trigger_type == "contains_any" if listener else False
            )
        ]
        
        self.trigger_select = discord.ui.Select(
            placeholder="Select Trigger Type",
            options=trigger_options,
            min_values=1,
            max_values=1
        )
        self.add_item(self.trigger_select)
        
        # Add action type selector
        action_options = [
            discord.SelectOption(
                label="Reply",
                description="Reply with a message in the channel",
                value="reply",
                default=listener.action_type == "reply" if listener else True
            ),
            discord.SelectOption(
                label="React",
                description="Add a reaction to the message",
                value="react",
                default=listener.action_type == "react" if listener else False
            ),
            discord.SelectOption(
                label="Direct Message",
                description="Send a DM to the user",
                value="dm",
                default=listener.action_type == "dm" if listener else False
            ),
            discord.SelectOption(
                label="Webhook",
                description="Send message via webhook (custom name/avatar)",
                value="webhook",
                default=listener.action_type == "webhook" if listener else False
            )
        ]
        
        self.action_select = discord.ui.Select(
            placeholder="Select Action Type",
            options=action_options,
            min_values=1,
            max_values=1
        )
        self.add_item(self.action_select)
        
        # Add open configuration button
        self.add_item(discord.ui.Button(
            label="Advanced Settings",
            style=discord.ButtonStyle.secondary,
            custom_id="advanced_settings"
        ))
        
        # Add save button
        self.add_item(discord.ui.Button(
            label="Create Listener" if not listener else "Save Changes",
            style=discord.ButtonStyle.success,
            custom_id="save_listener"
        ))
        
        # Add cancel button
        self.add_item(discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            custom_id="cancel"
        ))
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Handle button interactions"""
        # Get the custom_id of the button that was clicked
        custom_id = interaction.data.get("custom_id", "")
        
        if custom_id == "advanced_settings":
            # Open advanced settings modal or message
            await interaction.response.send_message(
                "Advanced settings are not yet implemented. Please use slash commands for advanced configuration.",
                ephemeral=True
            )
            return False
            
        elif custom_id == "save_listener":
            # Open the creation/edit modal
            await interaction.response.send_modal(
                ListenerModal(
                    self.cog,
                    self.listener,
                    title="Configure Message Listener"
                )
            )
            return False
            
        elif custom_id == "cancel":
            # Cancel the operation
            await interaction.response.edit_message(
                content="Operation cancelled.",
                view=None
            )
            return False
            
        # Allow other interactions to proceed
        return True

class MessageListenersCog(commands.Cog):
    """
    A cog for handling configurable message listeners that respond to different triggers.
    """
    
    def __init__(self, bot, logger):
        self.bot = bot
        self.logger = logger
        self.listeners: List[MessageListener] = []
        self.listeners_file = "data/files/message_listeners.json"
        self.custom_actions: Dict[str, Callable] = {}
        
        # Create the listener command group
        self.listener_group = app_commands.Group(
            name="listener", 
            description="Manage message listeners",
            default_permissions=discord.Permissions(administrator=True)
        )
        
        # Load listeners from file or initialize with defaults
        self._load_listeners()
        
        # Register custom actions
        self._register_custom_actions()
        
        # Add commands to the group
        self._setup_commands()
    
    def _setup_commands(self):
        """Set up all the commands in the listener group"""
        
        # ADD command
        @self.listener_group.command(name="add", description="Add a new message listener")
        @app_commands.default_permissions(administrator=True)
        async def listener_add(interaction: discord.Interaction):
            """Add a new message listener interactively"""
            # Check admin permissions
            if not await self._check_admin(interaction):
                return
                
            # Create and send the configuration view
            view = ListenerConfigView(self)
            await interaction.response.send_message(
                "📝 **Create a New Message Listener**\n"
                "Configure the options below and click 'Create Listener' when ready.",
                view=view,
                ephemeral=True
            )
        
        # REMOVE command
        @self.listener_group.command(name="remove", description="Remove a message listener")
        @app_commands.default_permissions(administrator=True)
        @app_commands.describe(name="Name of the listener to remove")
        async def listener_remove(interaction: discord.Interaction, name: str):
            """Remove a message listener by name"""
            # Check admin permissions
            if not await self._check_admin(interaction):
                return
                
            # Check if listener exists
            listener = self.get_listener(name)
            if not listener:
                await interaction.response.send_message(
                    f"❌ Listener '{name}' not found. Use `/listener list` to see available listeners.",
                    ephemeral=True
                )
                return
                
            # Remove the listener
            self.remove_listener(name)
            await interaction.response.send_message(
                f"✅ Listener '{name}' has been removed successfully!",
                ephemeral=True
            )
        
        # LIST command
        @self.listener_group.command(name="list", description="List all message listeners")
        @app_commands.default_permissions(administrator=True)
        async def listener_list(interaction: discord.Interaction):
            """List all message listeners"""
            # Check admin permissions
            if not await self._check_admin(interaction):
                return
                
            await interaction.response.defer(ephemeral=True)
            
            # Create an embed to display the listeners
            embed = discord.Embed(
                title="Message Listeners",
                description=f"Total Listeners: {len(self.listeners)}",
                color=discord.Color.blue()
            )
            
            # Sort listeners by name
            sorted_listeners = sorted(self.listeners, key=lambda l: l.name)
            
            # Add each listener to the embed
            for listener in sorted_listeners:
                status = "✅ Enabled" if listener.enabled else "❌ Disabled"
                trigger_info = f"{listener.trigger_type.capitalize()}: "
                
                # Format trigger_value differently based on type
                if listener.trigger_type == 'regex':
                    if hasattr(listener.trigger_value, 'pattern'):
                        trigger_info += f"`{listener.trigger_value.pattern}`"
                    else:
                        trigger_info += f"`{listener.trigger_value}`"
                elif isinstance(listener.trigger_value, list):
                    # For lists like contains_any, show first few elements
                    if len(listener.trigger_value) > 3:
                        trigger_info += f"`{', '.join(listener.trigger_value[:3])}...`"
                    else:
                        trigger_info += f"`{', '.join(listener.trigger_value)}`"
                else:
                    trigger_info += f"`{listener.trigger_value}`"
                    
                # Add a field for this listener
                embed.add_field(
                    name=f"{listener.name} - {status}",
                    value=f"**Description:** {listener.description}\n"
                          f"**Trigger:** {trigger_info}\n"
                          f"**Action:** {listener.action_type}\n"
                          f"**Chance:** {listener.chance:.0%}",
                    inline=False
                )
            
            # If no listeners, add a note
            if not self.listeners:
                embed.add_field(
                    name="No Listeners Found",
                    value="Use `/listener add` to create a new message listener.",
                    inline=False
                )
                
            # Add usage instructions
            embed.add_field(
                name="Managing Listeners",
                value="/listener add - Create a new listener\n"
                      "/listener edit - Edit an existing listener\n"
                      "/listener remove - Remove a listener\n"
                      "/listener toggle - Enable/disable a listener",
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        
        # EDIT command
        @self.listener_group.command(name="edit", description="Edit a message listener")
        @app_commands.default_permissions(administrator=True)
        @app_commands.describe(name="Name of the listener to edit")
        async def listener_edit(interaction: discord.Interaction, name: str):
            """Edit an existing message listener"""
            # Check admin permissions
            if not await self._check_admin(interaction):
                return
                
            # Check if listener exists
            listener = self.get_listener(name)
            if not listener:
                await interaction.response.send_message(
                    f"❌ Listener '{name}' not found. Use `/listener list` to see available listeners.",
                    ephemeral=True
                )
                return
                
            # Create and send the configuration view
            view = ListenerConfigView(self, listener)
            await interaction.response.send_message(
                f"📝 **Edit Message Listener: {name}**\n"
                "Configure the options below and click 'Save Changes' when ready.",
                view=view,
                ephemeral=True
            )
        
        # TOGGLE command
        @self.listener_group.command(name="toggle", description="Enable or disable a message listener")
        @app_commands.default_permissions(administrator=True)
        @app_commands.describe(
            name="Name of the listener to toggle",
            enabled="Whether to enable or disable the listener"
        )
        async def listener_toggle(interaction: discord.Interaction, name: str, enabled: bool):
            """Enable or disable a message listener"""
            # Check admin permissions
            if not await self._check_admin(interaction):
                return
                
            # Check if listener exists
            listener = self.get_listener(name)
            if not listener:
                await interaction.response.send_message(
                    f"❌ Listener '{name}' not found. Use `/listener list` to see available listeners.",
                    ephemeral=True
                )
                return
                
            # Toggle the listener
            self.enable_listener(name, enabled)
            status = "enabled" if enabled else "disabled"
            await interaction.response.send_message(
                f"✅ Listener '{name}' has been {status}!",
                ephemeral=True
            )
        
        # ADVANCED command
        @self.listener_group.command(name="advanced", description="Configure advanced settings for a message listener")
        @app_commands.default_permissions(administrator=True)
        @app_commands.describe(
            name="Name of the listener to configure",
            chance="Probability (0-100) that the listener will trigger when conditions are met",
            cooldown="Cooldown in seconds between triggers for the same user",
            require_mention="Whether the bot must be mentioned for this to trigger"
        )
        async def listener_advanced(
            interaction: discord.Interaction, 
            name: str, 
            chance: Optional[int] = None,
            cooldown: Optional[int] = None,
            require_mention: Optional[bool] = None
        ):
            """Configure advanced settings for a message listener"""
            # Check admin permissions
            if not await self._check_admin(interaction):
                return
                
            # Check if listener exists
            listener = self.get_listener(name)
            if not listener:
                await interaction.response.send_message(
                    f"❌ Listener '{name}' not found. Use `/listener list` to see available listeners.",
                    ephemeral=True
                )
                return
                
            # Build update kwargs
            updates = {}
            if chance is not None:
                # Convert percentage to decimal
                updates["chance"] = max(0.0, min(1.0, chance / 100))
            if cooldown is not None:
                updates["cooldown"] = max(0, cooldown)
            if require_mention is not None:
                updates["require_mention"] = require_mention
                
            # Update the listener
            if updates:
                self.update_listener(name, **updates)
                
                # Build response message
                response_parts = []
                if "chance" in updates:
                    response_parts.append(f"Chance: {updates['chance']:.0%}")
                if "cooldown" in updates:
                    response_parts.append(f"Cooldown: {updates['cooldown']}s")
                if "require_mention" in updates:
                    response_parts.append(f"Require Mention: {updates['require_mention']}")
                    
                await interaction.response.send_message(
                    f"✅ Listener '{name}' advanced settings updated!\n" + 
                    "\n".join(response_parts),
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"No changes made to listener '{name}'.",
                    ephemeral=True
                )
        
        # Add the autocomplete function for listener names
        async def listener_name_autocomplete(
            interaction: discord.Interaction,
            current: str,
        ) -> List[app_commands.Choice[str]]:
            """Autocomplete for listener names"""
            return [
                app_commands.Choice(name=listener.name, value=listener.name)
                for listener in self.listeners
                if current.lower() in listener.name.lower()
            ][:25]  # Discord limits to 25 choices
        
        # Apply the autocomplete to all relevant commands
        listener_edit.autocomplete("name")(listener_name_autocomplete)
        listener_remove.autocomplete("name")(listener_name_autocomplete)
        listener_toggle.autocomplete("name")(listener_name_autocomplete)
        listener_advanced.autocomplete("name")(listener_name_autocomplete)
    
    def _register_custom_actions(self):
        """
        Register custom action handlers. These can be called by name from listeners.
        """
        # Example custom action - increase a counter for a user
        # Custom actions would be functions that take (bot, message) and return None
        pass
    
    def _load_listeners(self):
        """Load message listeners from JSON file"""
        try:
            if os.path.exists(self.listeners_file):
                with open(self.listeners_file, 'r') as f:
                    listeners_data = json.load(f)
                    
                self.listeners = [MessageListener.from_dict(listener_data) for listener_data in listeners_data]
                self.logger.info(f"Loaded {len(self.listeners)} message listeners from {self.listeners_file}")
            else:
                # Initialize with default listeners if file doesn't exist
                self._initialize_default_listeners()
                self._save_listeners()
        except Exception as e:
            self.logger.error(f"Error loading message listeners: {e}", exc_info=True)
            # Initialize with defaults if there's an error
            self._initialize_default_listeners()
    
    def _save_listeners(self):
        """Save message listeners to JSON file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.listeners_file), exist_ok=True)
            
            # Convert listeners to dict and save
            listeners_data = [listener.to_dict() for listener in self.listeners]
            with open(self.listeners_file, 'w') as f:
                json.dump(listeners_data, f, indent=4)
                
            self.logger.info(f"Saved {len(self.listeners)} message listeners to {self.listeners_file}")
            return True
        except Exception as e:
            self.logger.error(f"Error saving message listeners: {e}", exc_info=True)
            return False
    
    def _initialize_default_listeners(self):
        """Initialize with some default message listeners"""
        self.listeners = [
            # The original "hello bot" listener
            MessageListener(
                name="hello_bot",
                description="Responds when someone says 'hello bot'",
                trigger_type="contains",
                trigger_value="hello bot",
                action_type="reply",
                action_value="Hello {user.mention}! I'm listening to events in my message listeners cog.",
                ignore_case=True,
                enabled=True
            ),
            
            # A few additional example listeners
            MessageListener(
                name="thank_you",
                description="Responds with a reaction when someone says thank you",
                trigger_type="contains_any",
                trigger_value=["thank you", "thanks", "thx"],
                action_type="react",
                action_value="👍",
                chance=0.8,
                ignore_case=True,
                enabled=True
            ),
            
            MessageListener(
                name="good_morning",
                description="Responds to morning greetings",
                trigger_type="contains_any",
                trigger_value=["good morning", "morning everyone", "morning all"],
                action_type="reply",
                action_value="Good morning, {user}! Rise and shine! ☀️",
                cooldown=300,  # 5 minutes cooldown
                ignore_case=True,
                enabled=True
            ),
            
            MessageListener(
                name="dice_roll",
                description="Roll a virtual dice when asked",
                trigger_type="regex",
                trigger_value=r"roll\s+a\s+d(\d+)",
                action_type="reply",
                action_value="🎲 {user} rolled a {random.number:1:20}!",
                ignore_case=True,
                enabled=True
            )
        ]
        
        self.logger.info(f"Initialized {len(self.listeners)} default message listeners")
    
    def add_listener(self, listener: MessageListener) -> bool:
        """Add a new message listener"""
        # Check for duplicate names
        if any(l.name == listener.name for l in self.listeners):
            return False
            
        self.listeners.append(listener)
        self._save_listeners()
        return True
    
    def remove_listener(self, name: str) -> bool:
        """Remove a message listener by name"""
        initial_count = len(self.listeners)
        self.listeners = [l for l in self.listeners if l.name != name]
        
        if len(self.listeners) < initial_count:
            self._save_listeners()
            return True
        return False
    
    def get_listener(self, name: str) -> Optional[MessageListener]:
        """Get a listener by name"""
        for listener in self.listeners:
            if listener.name == name:
                return listener
        return None
    
    def update_listener(self, name: str, **kwargs) -> bool:
        """Update a listener with new values"""
        listener = self.get_listener(name)
        if not listener:
            return False
            
        for key, value in kwargs.items():
            if hasattr(listener, key):
                setattr(listener, key, value)
                
        self._save_listeners()
        return True
    
    def enable_listener(self, name: str, enabled: bool = True) -> bool:
        """Enable or disable a listener"""
        return self.update_listener(name, enabled=enabled)
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Event listener for all messages.
        Checks all registered listeners and executes their actions if triggered.
        """
        # Don't respond to messages from bots (including self)
        if message.author.bot:
            return
            
        # Process all registered listeners
        for listener in self.listeners:
            if listener.should_trigger(message):
                self.logger.debug(f"Listener '{listener.name}' triggered by message: {message.content}")
                await listener.execute_action(self.bot, message)
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Called when the bot is ready"""
        self.logger.info(f"Message Listeners Cog ready with {len(self.listeners)} active listeners")

    # ----- Helper Methods -----
    
    async def _check_admin(self, interaction: discord.Interaction) -> bool:
        """Check if the user has admin permissions"""
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return False
            
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command.", ephemeral=True)
            return False
            
        return True
    
    async def cog_load(self):
        """
        Called when the cog is loaded.
        Register the command group with the bot's command tree.
        """
        self.bot.tree.add_command(self.listener_group)
        self.logger.info("Listener command group registered")

def setup(bot):
    """Setup function for loading the cog"""
    # Get the logger from the bot if available
    logger = getattr(bot, "logger", None)
    if not logger:
        import logging
        logger = logging.getLogger("discord.message_listeners")
        
    bot.add_cog(MessageListenersCog(bot, logger))