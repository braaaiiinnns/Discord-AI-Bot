"""
Core Discord bot implementation.
This module contains the main DiscordBot class that initializes and runs the Discord bot.
"""

import discord
import logging
import os
import asyncio
import datetime
from discord import app_commands
from discord.ext import commands
from discord.utils import get
from config.config import (
    DISCORD_BOT_TOKEN, OPENAI_API_KEY, GOOGLE_GENAI_API_KEY, CLAUDE_API_KEY, 
    GROK_API_KEY, TIMEZONE, MESSAGES_DB_PATH, AI_INTERACTIONS_DB_PATH,
    ENCRYPTION_KEY, ENABLE_MESSAGE_LOGGING, ENABLE_AI_LOGGING,
    ENABLE_DASHBOARD, DASHBOARD_HOST, DASHBOARD_PORT, DASHBOARD_REQUIRE_LOGIN
)
from utils.logger import setup_logger
from utils.ai_services import get_openai_client, get_google_genai_client, get_claude_client, get_grok_client
from app.discord.state import BotState
from app.discord.task_scheduler import TaskScheduler
from app.discord.role_color_manager import RoleColorManager
from app.discord.task_manager import TaskManager
from app.discord.message_monitor import MessageMonitor
from utils.ai_logger import AIInteractionLogger
from app.discord.cogs import PremiumRolesCog, UserStateCog, ImageGeneration, Dashboard, RoleColorCog, MessageListenersCog
from app.discord.cogs.gen_ai_cog import AICogCommands

class DiscordBot:
    """Main Discord bot class that initializes and runs the bot"""
    
    def __init__(self):
        # Setup logging
        self.logger = setup_logger()
        self.logger.info("Initializing Discord bot")
        
        # Configure Discord client
        self.intents = discord.Intents.all()
        # Use Bot instead of AutoShardedClient for cogs support
        self.client = commands.Bot(command_prefix="!", intents=self.intents, tree_cls=app_commands.CommandTree)
        self.tree = self.client.tree
        self.bot_state = BotState(timeout=3600)
        self.response_channels = {}  # Cache response channels by guild ID
        
        # Initialize message and AI logging services
        self._init_logging_services()
        
        # Initialize task infrastructure
        self._init_task_infrastructure()
        
        # Initialize AI clients
        self._init_ai_clients()
        
        # Register setup hook for async initialization
        self.client.setup_hook = self._setup_hook
    
    def _init_logging_services(self):
        """Initialize message monitoring and AI logging services"""
        try:
            # Ensure data directory exists
            os.makedirs(os.path.dirname(MESSAGES_DB_PATH), exist_ok=True)
            
            # Initialize message monitor if enabled
            self.message_monitor = None
            if ENABLE_MESSAGE_LOGGING:
                self.message_monitor = MessageMonitor(
                    self.client,
                    MESSAGES_DB_PATH,
                    ENCRYPTION_KEY,
                    vision_api_key=GOOGLE_GENAI_API_KEY  # Pass Gemini API key for image analysis
                )
                self.logger.info("Message monitoring service initialized" + 
                                (" with AI content analysis" if GOOGLE_GENAI_API_KEY else ""))
            
            # Initialize AI logger if enabled
            self.ai_logger = None
            if ENABLE_AI_LOGGING:
                self.ai_logger = AIInteractionLogger(
                    AI_INTERACTIONS_DB_PATH,
                    ENCRYPTION_KEY
                )
                self.logger.info("AI interaction logging service initialized")
                
            # Initialize dashboard if enabled
            self.dashboard = None
            if ENABLE_DASHBOARD and self.message_monitor:
                # Import the dashboard module here to avoid circular imports
                from app.dashboard.dashboard import Dashboard
                self.dashboard = Dashboard(
                    message_monitor=self.message_monitor,
                    port=DASHBOARD_PORT,
                    require_auth=DASHBOARD_REQUIRE_LOGIN,
                    secret_key=ENCRYPTION_KEY
                )
                self.logger.info(f"Dashboard initialized with Discord SSO authentication")
                
        except Exception as e:
            self.logger.error(f"Error initializing logging services: {e}", exc_info=True)
            # Continue without logging services if they fail to initialize
            self.message_monitor = None
            self.ai_logger = None
            self.dashboard = None
        
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
    
    async def _setup_hook(self):
        """Async setup hook for initializing cogs"""
        self.logger.info("Loading cogs...")
        
        # AI Commands Cog
        ai_cog = AICogCommands(
            self.client, 
            self.bot_state, 
            self.response_channels, 
            self.logger, 
            self.ai_logger if hasattr(self, 'ai_logger') and self.ai_logger else None
        )
        ai_cog.setup_clients(
            self.openai_client, 
            self.google_client, 
            self.claude_client, 
            self.grok_client
        )
        await self.client.add_cog(ai_cog)
        self.logger.info("AI commands cog loaded")
        
        # Premium Roles Cog
        premium_roles_cog = PremiumRolesCog(
            self.client,
            self.logger
        )
        await self.client.add_cog(premium_roles_cog)
        self.logger.info("Premium roles cog loaded")
        
        # User State Cog
        user_state_cog = UserStateCog(
            self.client,
            self.bot_state,
            self.logger
        )
        await self.client.add_cog(user_state_cog)
        self.logger.info("User state cog loaded")
        
        # Image Generation Cog
        image_gen_cog = ImageGeneration(
            self.client,
            self.logger
        )
        image_gen_cog.setup_clients(self.openai_client)
        await self.client.add_cog(image_gen_cog)
        self.logger.info("Image generation cog loaded")
        
        # Dashboard Cog
        dashboard_cog = Dashboard(
            self.client,
            self.logger
        )
        await self.client.add_cog(dashboard_cog)
        self.logger.info("Dashboard cog loaded")
        
        # Role Color Cog
        role_color_cog = RoleColorCog(
            self.client,
            self.role_color_manager,
            self.logger
        )
        await self.client.add_cog(role_color_cog)
        self.logger.info("Role color cog loaded")
        
        # Message Listeners Cog
        message_listeners_cog = MessageListenersCog(
            self.client,
            self.logger
        )
        await self.client.add_cog(message_listeners_cog)
        self.logger.info("Message listeners cog loaded")
        
        # Schedule daily color cycle update
        self._schedule_color_cycle_task(role_color_cog)
        
        self.logger.info("All cogs loaded successfully")
    
    def _schedule_color_cycle_task(self, role_color_cog):
        """Schedule the daily color cycle task"""
        # Schedule for early morning (3:00 AM) to not interfere with other tasks
        time = datetime.time(hour=3, minute=0)
        
        # Create a task for the color cycle update
        task_id = self.scheduler.schedule_at_time(
            role_color_cog.update_role_color_from_cycle,
            time=time,
            task_id="role_color_cycle_update",
            use_timezone=True
        )
        
        # Start the task
        self.scheduler.start_task(task_id)
        self.logger.info(f"Role color cycle task scheduled with ID: {task_id} at {time} {TIMEZONE}")
    
    def run(self):
        """Run the Discord bot"""
        @self.client.event
        async def on_ready():
            self.logger.info(f"Logged in as {self.client.user}")
            
            # Cache response channels
            await self._find_or_create_response_channels()
            
            # Register scheduled tasks
            self.task_manager.register_tasks(self.tree)
            
            # Sync commands with Discord
            self.logger.info("Syncing commands with Discord...")
            
            # Add retry mechanism for command sync
            max_retries = 3
            retry_count = 0
            sync_success = False
            
            while not sync_success and retry_count < max_retries:
                try:
                    await self.tree.sync()
                    sync_success = True
                    self.logger.info("Commands synced successfully")
                    
                    # Log registered commands
                    commands = self.tree.get_commands()
                    command_names = [cmd.name for cmd in commands]
                    self.logger.info(f"Registered commands: {', '.join(command_names)}")
                except Exception as e:
                    retry_count += 1
                    self.logger.error(f"Failed to sync commands (attempt {retry_count}/{max_retries}): {e}", exc_info=True)
                    await asyncio.sleep(2)  # Wait before retrying
            
            if not sync_success:
                self.logger.warning("Could not sync commands after multiple attempts. Bot will use cached commands.")
            
            # Start scheduled tasks
            self.task_manager.start_tasks()
            self.logger.info("Scheduled tasks started")
            
            # Start dashboard if enabled
            if self.dashboard:
                dashboard_url = self.dashboard.start()
                self.logger.info(f"Dashboard started at {dashboard_url}")
        
        # Register message monitoring events if enabled
        if self.message_monitor:
            @self.client.event
            async def on_message(message):
                try:
                    # Don't process messages from the bot itself
                    if message.author == self.client.user:
                        return
                    
                    # Log the message
                    await self.message_monitor.process_message(message)
                    
                    # Process commands (important for cogs to receive messages)
                    await self.client.process_commands(message)
                except Exception as e:
                    self.logger.error(f"Error processing message event: {e}", exc_info=True)
            
            @self.client.event
            async def on_message_delete(message):
                try:
                    await self.message_monitor.process_message_delete(message)
                except Exception as e:
                    self.logger.error(f"Error processing message delete event: {e}", exc_info=True)
            
            @self.client.event
            async def on_message_edit(before, after):
                try:
                    await self.message_monitor.process_message_edit(before, after)
                except Exception as e:
                    self.logger.error(f"Error processing message edit event: {e}", exc_info=True)
        
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

    def cleanup(self):
        """Clean up resources before shutting down"""
        try:
            # Stop the dashboard if it's running
            if hasattr(self, 'dashboard') and self.dashboard:
                self.dashboard.stop()
                self.logger.info("Dashboard stopped")
            
            # Close database connections
            if hasattr(self, 'message_monitor') and self.message_monitor:
                self.message_monitor.close()
                self.logger.info("Message monitor closed")
                
            if hasattr(self, 'ai_logger') and self.ai_logger:
                self.ai_logger.close()
                self.logger.info("AI logger closed")
            
            # Clean up AI clients
            if hasattr(self, 'openai_client'):
                self.openai_client = None
            if hasattr(self, 'google_client'):
                self.google_client = None
            if hasattr(self, 'claude_client'):
                self.claude_client = None
            if hasattr(self, 'grok_client'):
                self.grok_client = None
            self.logger.info("AI clients cleaned up")
            
            # Clean up task scheduler
            if hasattr(self, 'task_scheduler') and self.task_scheduler:
                self.task_scheduler.stop()
                self.logger.info("Task scheduler stopped")
                
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}", exc_info=True)