import discord
import logging
from discord import app_commands
from discord.utils import get
from config import DISCORD_BOT_TOKEN, OPENAI_API_KEY, GOOGLE_GENAI_API_KEY, CLAUDE_API_KEY, GROK_API_KEY, TIMEZONE
from logger_config import setup_logger
from ai_services import get_openai_client, get_google_genai_client, get_claude_client, get_grok_client
from state import BotState
from discord_commands import BotCommands
from task_scheduler import TaskScheduler
from role_color_manager import RoleColorManager
from task_manager import TaskManager

class DiscordBot:
    """Main Discord bot class that initializes and runs the bot"""
    
    def __init__(self):
        # Setup logging
        self.logger = setup_logger()
        self.logger.info("Initializing Discord bot")
        
        # Configure Discord client
        self.intents = discord.Intents.all()
        self.client = discord.AutoShardedClient(intents=self.intents)
        self.tree = app_commands.CommandTree(self.client)
        self.bot_state = BotState(timeout=3600)
        self.response_channels = {}  # Cache response channels by guild ID
        
        # Initialize task infrastructure
        self._init_task_infrastructure()
        
        # Initialize AI clients
        self._init_ai_clients()
        
        # Initialize command handler
        self.command_handler = BotCommands(
            self.client,
            self.bot_state,
            self.tree,
            self.response_channels,
            self.logger
        )
        
    def _init_task_infrastructure(self):
        """Initialize task scheduling infrastructure"""
        # Initialize the task scheduler with timezone
        self.scheduler = TaskScheduler(self.client, timezone=TIMEZONE)
        self.logger.info(f"Task scheduler initialized with timezone: {TIMEZONE}")
        
        # Initialize the task manager
        self.task_manager = TaskManager(self.client, self.scheduler, self.logger)
        
        # Initialize the role color manager
        self.role_color_manager = RoleColorManager(self.client, self.scheduler)
        
        # Register the role color manager with the task manager
        self.task_manager.register_role_color_manager(self.role_color_manager)
        self.logger.info("Task infrastructure initialized")
    
    def _init_ai_clients(self):
        """Initialize AI service clients"""
        self.openai_client = get_openai_client(OPENAI_API_KEY)
        self.google_client = get_google_genai_client(GOOGLE_GENAI_API_KEY)
        self.claude_client = get_claude_client(CLAUDE_API_KEY)
        self.grok_client = get_grok_client(GROK_API_KEY)
        self.logger.info("AI clients initialized")
    
    def _register_commands(self):
        """Register all bot commands and tasks"""
        # Register AI commands
        self.command_handler.register_commands(
            self.openai_client,
            self.google_client,
            self.claude_client,
            self.grok_client
        )
        
        # Register scheduled tasks and their commands
        self.task_manager.register_tasks(self.tree)
        
        self.logger.info("All commands and tasks registered")
    
    def run(self):
        """Run the Discord bot"""
        @self.client.event
        async def on_ready():
            self.logger.info(f"Logged in as {self.client.user}")
            
            # Cache response channels
            await self._find_or_create_response_channels()
            
            # Sync commands with Discord
            self.logger.info("Syncing commands with Discord...")
            try:
                await self.tree.sync()
                self.logger.info("Commands synced successfully")
                
                # Log registered commands
                commands = self.tree.get_commands()
                command_names = [cmd.name for cmd in commands]
                self.logger.info(f"Registered commands: {', '.join(command_names)}")
            except Exception as e:
                self.logger.error(f"Failed to sync commands: {e}", exc_info=True)
            
            # Start scheduled tasks
            self.task_manager.start_tasks()
            self.logger.info("Scheduled tasks started")
        
        # Register commands
        self._register_commands()
        
        # Run the client
        self.logger.info("Starting Discord bot")
        self.client.run(DISCORD_BOT_TOKEN)
    
    async def _find_or_create_response_channels(self):
        """Find or create the response channel in all guilds"""
        for guild in self.client.guilds:
            self.logger.info(f"Finding/creating response channel in {guild.name}")
            
            # Try to find the "🤖" channel
            response_channel = discord.utils.get(guild.text_channels, name="🤖")
            
            # Create the channel if it doesn't exist
            if not response_channel:
                try:
                    response_channel = await guild.create_text_channel("🤖")
                    self.logger.info(f"Created response channel in {guild.name}")
                except Exception as e:
                    self.logger.error(f"Failed to create response channel in {guild.name}: {e}", exc_info=True)
                    continue
            
            # Cache the channel
            self.response_channels[guild.id] = response_channel
            self.logger.info(f"Response channel cached for {guild.name}: {response_channel.name} (ID: {response_channel.id})")

if __name__ == "__main__":
    bot = DiscordBot()
    bot.run()