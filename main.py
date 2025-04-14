import discord
import logging  # Ensure logging is imported
from discord import app_commands
from discord.utils import get  # Import utility for searching channels
from config import DISCORD_BOT_TOKEN, OPENAI_API_KEY, GOOGLE_GENAI_API_KEY, CLAUDE_API_KEY, GROK_API_KEY
from logger_config import setup_logger
from clients import get_openai_client, get_google_genai_client, get_claude_client, get_grok_client
from state import BotState
from commands import CommandHandler, CommandGroup  # Import CommandGroup
from task_scheduler import TaskScheduler  # Import generic scheduler
from role_color_scheduler import RoleColorManager  # Import renamed role color manager

class DiscordBot:
    def __init__(self):
        self.logger = setup_logger()  # Ensure logger is initialized using setup_logger
        
        # Configure intents
        self.intents = discord.Intents.all()  # Initialize intents
        
        self.client = discord.AutoShardedClient(intents=self.intents)
        self.tree = app_commands.CommandTree(self.client)
        self.bot_state = BotState(timeout=3600)
        self.response_channels = {}  # Cache response channels by guild ID

        # Initialize the generic task scheduler
        self.scheduler = TaskScheduler(self.client)
        
        # Initialize the role color manager with the scheduler
        self.role_color_manager = RoleColorManager(self.client, self.scheduler)

        # Pass response_channels to CommandHandler
        self.command_handler = CommandHandler(
            self.bot_state, 
            self.tree, 
            self.response_channels, 
            self.logger,
            self.role_color_manager  # Pass the role color manager
        )

        # Initialize API clients
        self.openai_client = get_openai_client(OPENAI_API_KEY)
        self.google_client = get_google_genai_client(GOOGLE_GENAI_API_KEY)
        self.claude_client = get_claude_client(CLAUDE_API_KEY)
        self.grok_client = get_grok_client(GROK_API_KEY)

        # Register commands
        self.command_handler.register_commands(
            self.client, self.openai_client, self.google_client, self.claude_client, self.grok_client
        )

    def run(self):
        @self.client.event
        async def on_ready():
            self.logger.info(f"Logged in as {self.client.user}")
            self.logger.info("Syncing commands with Discord...")
            try:
                # Sync commands globally
                await self.tree.sync()
                self.logger.info("Commands synced successfully.")
            except Exception as e:
                self.logger.error(f"Failed to sync commands: {e}", exc_info=True)

            # Log registered commands after syncing
            self.logger.info("Registered commands:")
            for command in self.tree.get_commands():
                self.logger.info(f"- {command.name}")

            # Search for or create the "🤖" channel in all guilds
            for guild in self.client.guilds:
                response_channel = discord.utils.get(guild.text_channels, name="🤖")
                if response_channel:
                    self.logger.info(f"Response channel found: {response_channel.name} (ID: {response_channel.id}) in guild {guild.name}")
                else:
                    try:
                        response_channel = await guild.create_text_channel("🤖")
                        self.logger.info(f"Created response channel: {response_channel.name} (ID: {response_channel.id}) in guild {guild.name}")
                    except Exception as e:
                        self.logger.error(f"Failed to create response channel in guild {guild.name}: {e}", exc_info=True)

                # Cache the response channel for the guild
                self.response_channels[guild.id] = response_channel

                self.logger.info(f"Response channel cached for guild '{guild.name}': {response_channel.name} (ID: {response_channel.id})")
            
            # Start the role color manager
            self.role_color_manager.start()
            
            # We could schedule other tasks here as examples
            self.scheduler.schedule_interval(
                self.example_interval_task, 
                hours=1,  # Run every hour
                task_id="hourly_example_task"
            )
            
            # Start all scheduled tasks
            self.scheduler.start_all()

        # Run the bot
        self.client.run(DISCORD_BOT_TOKEN)
    
    async def example_interval_task(self):
        """An example task that runs at an interval"""
        self.logger.info("Running example interval task")
        # This is just a placeholder method


class CommandHandler:
    """Main command handler for registering commands."""
    def __init__(self, bot_state: BotState, tree: discord.app_commands.CommandTree, 
                 response_channels: dict, logger: logging.Logger, 
                 role_color_manager: RoleColorManager):
        self.logger = logger  # Use the logger passed from DiscordBot
        self.bot_state = bot_state
        self.tree = tree
        self.response_channels = response_channels  # Store response_channels
        self.role_color_manager = role_color_manager  # Store the role color manager

    def register_commands(self, client: discord.Client, openai_client, google_client, claude_client, grok_client):
        # Register the /ask command group
        self.tree.add_command(CommandGroup(
            bot_state=self.bot_state,
            logger=self.logger,
            client=client,  # Pass the client object
            openai_client=openai_client,
            google_client=google_client,
            claude_client=claude_client,
            grok_client=grok_client,  # Pass the Grok client
            response_channels=self.response_channels  # Pass the response channels
        ))
        self.logger.info("Registered /ask command group.")

        # Register the /clear_history command
        @self.tree.command(name="clear_history", description="Clear your conversation history")
        async def clear_history(interaction: discord.Interaction):
            self.logger.info(f"User {interaction.user} invoked /clear_history")
            uid = str(interaction.user.id)
            user_state = self.bot_state.get_user_state(uid)
            user_state.clear_history()
            self.logger.info(f"Cleared history for user {interaction.user}")
            await interaction.response.send_message("Your conversation history has been cleared.")
            
        # Register the /change_role_color command
        @self.tree.command(name="change_role_color", description="Change the color of the configured role to a random color")
        @app_commands.default_permissions(manage_roles=True)
        async def change_role_color(interaction: discord.Interaction):
            self.logger.info(f"User {interaction.user} invoked /change_role_color")
            await interaction.response.defer()
            
            try:
                # Call the manual color change function
                success = await self.role_color_manager.change_role_color_now(interaction.guild_id)
                
                if success:
                    await interaction.followup.send("Role color changed successfully!")
                else:
                    await interaction.followup.send("Failed to change role color. Check if the role exists.")
            except Exception as e:
                self.logger.error(f"Error changing role color: {e}", exc_info=True)
                await interaction.followup.send("An error occurred while changing the role color.")

        # Example of scheduling a one-time task from a command
        @self.tree.command(name="remind_me", description="Set a reminder for later")
        async def remind_me(interaction: discord.Interaction, 
                           hours: int = 0, 
                           minutes: int = 0,
                           message: str = "Reminder!"):
            
            self.logger.info(f"User {interaction.user} set a reminder for {hours}h {minutes}m: {message}")
            
            # Define a callback for the reminder
            async def send_reminder(user_id, channel_id, reminder_message):
                user = client.get_user(int(user_id))
                channel = client.get_channel(int(channel_id))
                if channel:
                    await channel.send(f"<@{user_id}> Reminder: {reminder_message}")
                    self.logger.info(f"Sent reminder to user {user_id}")
            
            from task_scheduler import TaskScheduler
            scheduler = client._connection._get_client().scheduler
            
            # Schedule the reminder
            await scheduler.schedule_wait(
                send_reminder,
                hours=hours,
                minutes=minutes,
                user_id=str(interaction.user.id),
                channel_id=str(interaction.channel_id),
                reminder_message=message
            )
            
            total_minutes = hours * 60 + minutes
            await interaction.response.send_message(
                f"I'll remind you about '{message}' in {total_minutes} minutes!"
            )

if __name__ == "__main__":
    bot = DiscordBot()
    bot.run()