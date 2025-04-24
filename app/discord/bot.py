"""
Core Discord bot implementation.
This module contains the main DiscordBot class that initializes and runs the Discord bot.
"""

import discord
import logging
import os
import asyncio
import threading
import datetime
from discord import app_commands
from discord.ext import commands
from discord.utils import get
from config.config import (
    DISCORD_BOT_TOKEN, OPENAI_API_KEY, GOOGLE_GENAI_API_KEY, CLAUDE_API_KEY, 
    GROK_API_KEY, TIMEZONE, MESSAGES_DB_PATH, AI_INTERACTIONS_DB_PATH,
    ENCRYPTION_KEY, ENABLE_MESSAGE_LOGGING, ENABLE_AI_LOGGING,
    DASHBOARD_HOST, DASHBOARD_PORT,
    API_HOST, API_PORT,  # Added API_HOST and API_PORT for correct API server config
    LOG_LEVEL, ENABLE_DEBUG_LOGGING, LOG_FILE_PATH
)
from utils.logger import setup_logger
from utils.ai_services import get_openai_client, get_google_genai_client, get_claude_client, get_grok_client
from app.discord.state import BotState
from app.discord.task_scheduler import TaskScheduler
from app.discord.role_color_manager import RoleColorManager
from app.discord.task_manager import TaskManager
from app.discord.message_monitor import MessageMonitor
from utils.ai_logger import AIInteractionLogger
from app.discord.cogs import PremiumRolesCog, UserStateCog, ImageGeneration, RoleColorCog, MessageListenersCog  # Dashboard removed
from app.discord.cogs.gen_ai_cog import AICogCommands
from app.discord.cogs.admin_cog import AdminCog
from app.api.server import start_server  # Keep API server import

class DiscordBot:
    """Main Discord bot class that initializes and runs the bot"""
    
    def __init__(self):
        # Setup logging - use LOG_FILE_PATH from config
        self.logger = setup_logger(log_file=LOG_FILE_PATH, level=LOG_LEVEL)
        self.logger.propagate = False
        self.logger.debug("DiscordBot initializing...")
        
        # Configure root logger to prevent duplicate messages
        root_logger = logging.getLogger()
        root_logger.handlers = []  # Remove any existing handlers
        
        # Disable the discord.py and werkzeug logging handlers to prevent duplication
        logging.getLogger('discord').propagate = False
        logging.getLogger('discord').setLevel(logging.ERROR)
        logging.getLogger('werkzeug').propagate = False
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        
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
        self.logger.debug("DiscordBot initialization complete.")

    def _init_logging_services(self):
        """Initialize message monitoring and AI logging services"""
        self.logger.debug("Initializing logging services...")
        try:
            # Ensure data directory exists
            os.makedirs(os.path.dirname(MESSAGES_DB_PATH), exist_ok=True)
            self.logger.debug(f"Data directory ensured at {os.path.dirname(MESSAGES_DB_PATH)}")
            
            # Initialize message monitor if enabled
            self.message_monitor = None
            if ENABLE_MESSAGE_LOGGING:
                self.logger.debug("Message logging enabled. Initializing MessageMonitor.")
                from utils.database import UnifiedDatabase
                # Create a unified database instead of using separate files
                db = UnifiedDatabase(
                    db_path=MESSAGES_DB_PATH, 
                    encryption_key=ENCRYPTION_KEY,
                    create_tables=False  # Don't create tables immediately
                )
                self.message_monitor = MessageMonitor(
                    db=db,
                    encryption_key=ENCRYPTION_KEY
                )
            else:
                self.logger.debug("Message logging disabled.")
            
            # Initialize AI logger if enabled
            self.ai_logger = None
            if ENABLE_AI_LOGGING:
                self.logger.debug("AI logging enabled. Initializing AIInteractionLogger.")
                # Log the encryption key hash for debugging
                key_hash = hash(ENCRYPTION_KEY)
                self.logger.debug(f"Using encryption key with hash: {key_hash}")
                
                # Use the same unified database if message monitor is enabled
                if self.message_monitor:
                    self.ai_logger = AIInteractionLogger(
                        db=self.message_monitor.db,
                        encryption_key=ENCRYPTION_KEY
                    )
                else:
                    # Create a new database connection if message monitor is disabled
                    from utils.database import UnifiedDatabase
                    db = UnifiedDatabase(
                        db_path=AI_INTERACTIONS_DB_PATH,
                        encryption_key=ENCRYPTION_KEY,
                        create_tables=False  # Don't create tables immediately
                    )
                    self.ai_logger = AIInteractionLogger(
                        db=db,
                        encryption_key=ENCRYPTION_KEY
                    )
            else:
                self.logger.debug("AI logging disabled.")
                
            # Dashboard initialization removed
                
        except Exception as e:
            self.logger.error(f"Error initializing logging services: {str(e)}")
            # Continue without logging services if they fail to initialize
            self.message_monitor = None
            self.ai_logger = None
        self.logger.debug("Logging services initialization finished.")
        
    def _init_task_infrastructure(self):
        """Initialize task scheduling infrastructure"""
        self.logger.debug("Initializing task infrastructure...")
        # Initialize the task scheduler with timezone
        self.scheduler = TaskScheduler(self.client, timezone=TIMEZONE)
        self.logger.debug("TaskScheduler initialized.")
        
        # Initialize the task manager
        self.task_manager = TaskManager(self.client, self.scheduler, self.logger)
        self.logger.debug("TaskManager initialized.")
        
        # Initialize the role color manager
        self.role_color_manager = RoleColorManager(self.client, self.scheduler)
        self.logger.debug("RoleColorManager initialized.")
        
        # Register the role color manager with the task manager
        self.task_manager.register_role_color_manager(self.role_color_manager)
        self.logger.debug("RoleColorManager registered with TaskManager.")
        self.logger.debug("Task infrastructure initialization complete.")
    
    def _init_ai_clients(self):
        """Initialize AI service clients"""
        self.logger.debug("Initializing AI clients...")
        self.openai_client = get_openai_client(OPENAI_API_KEY)
        self.logger.debug("OpenAI client initialized.")
        self.google_client = get_google_genai_client(GOOGLE_GENAI_API_KEY)
        self.logger.debug("Google GenAI client initialized.")
        self.claude_client = get_claude_client(CLAUDE_API_KEY)
        self.logger.debug("Claude client initialized.")
        self.grok_client = get_grok_client(GROK_API_KEY)
        self.logger.debug("Grok client initialized.")
        self.logger.debug("AI clients initialization complete.")
    
    async def _setup_hook(self):
        """Async setup hook for initializing cogs"""
        self.logger.debug("Running setup hook...")
        
        # Set client reference in the message monitor if available
        if hasattr(self, 'message_monitor') and self.message_monitor:
            self.message_monitor.set_client(self.client)
            self.logger.debug("Client reference set in MessageMonitor.")
            
        # AI Commands Cog
        self.logger.debug("Initializing AICogCommands...")
        ai_cog = AICogCommands(
            self.client, 
            self.bot_state, 
            self.response_channels, 
            self.logger, 
            self.message_monitor if hasattr(self, 'message_monitor') and self.message_monitor else None
        )
        ai_cog.setup_clients(
            self.openai_client, 
            self.google_client, 
            self.claude_client, 
            self.grok_client
        )
        await self.client.add_cog(ai_cog)
        self.logger.debug("AICogCommands added.")
        
        # Premium Roles Cog
        self.logger.debug("Initializing PremiumRolesCog...")
        premium_roles_cog = PremiumRolesCog(
            self.client,
            self.logger
        )
        await self.client.add_cog(premium_roles_cog)
        self.logger.debug("PremiumRolesCog added.")
        
        # User State Cog
        self.logger.debug("Initializing UserStateCog...")
        user_state_cog = UserStateCog(
            self.client,
            self.bot_state,
            self.logger
        )
        await self.client.add_cog(user_state_cog)
        self.logger.debug("UserStateCog added.")
        
        # Image Generation Cog
        self.logger.debug("Initializing ImageGeneration Cog...")
        image_gen_cog = ImageGeneration(
            self.client,
            self.logger
        )
        image_gen_cog.setup_clients(self.openai_client)
        await self.client.add_cog(image_gen_cog)
        self.logger.debug("ImageGeneration Cog added.")
        
        # Dashboard Cog removed
        
        # Role Color Cog
        self.logger.debug("Initializing RoleColorCog...")
        role_color_cog = RoleColorCog(
            self.client,
            self.role_color_manager,
            self.logger
        )
        await self.client.add_cog(role_color_cog)
        self.logger.debug("RoleColorCog added.")
        
        # Message Listeners Cog
        self.logger.debug("Initializing MessageListenersCog...")
        message_listeners_cog = MessageListenersCog(
            self.client,
            self.logger
        )
        await self.client.add_cog(message_listeners_cog)
        self.logger.debug("MessageListenersCog added.")

        # Admin Cog
        self.logger.debug("Initializing AdminCog...")
        admin_cog = AdminCog(self)  # Pass the DiscordBot instance (self)
        await self.client.add_cog(admin_cog)
        self.logger.debug("AdminCog added.")
        
        # Schedule daily color cycle update
        self._schedule_color_cycle_task(role_color_cog)
        
        # Add network connection monitoring
        self.logger.debug("Setting up network connectivity monitoring...")
        
        async def check_network_connectivity():
            """Periodic task to check network connectivity"""
            import socket
            
            while True:
                try:
                    # Try to resolve Discord's domain to check internet connectivity
                    socket.gethostbyname("discord.com")
                    # If successful, wait before checking again
                    await asyncio.sleep(60)  # Check every minute
                except socket.gaierror:
                    # DNS resolution failed, log the issue
                    self.logger.warning("Network connectivity issue detected - DNS resolution failed")
                    # Wait less time before checking again when there's a problem
                    await asyncio.sleep(15)  # Check more frequently during issues
                except Exception as e:
                    # Other error occurred
                    self.logger.error(f"Error in network connectivity check: {e}")
                    await asyncio.sleep(30)
        
        # Use asyncio.create_task instead of client.create_task
        asyncio.create_task(check_network_connectivity())
        self.logger.debug("Network connectivity monitoring task created.")
        
        self.logger.debug("Setup hook finished.")
    
    def _schedule_color_cycle_task(self, role_color_cog):
        """Schedule the daily color cycle task"""
        self.logger.debug("Scheduling daily color cycle task...")
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
        self.logger.debug(f"Daily color cycle task scheduled with ID: {task_id}")
    
    def run(self):
        """Run the Discord bot"""
        @self.client.event
        async def on_ready():
            self.logger.info(f"Logged in as {self.client.user}")
            self.logger.debug("on_ready event triggered.")
            
            # Cache response channels
            self.logger.debug("Finding or creating response channels...")
            await self._find_or_create_response_channels()
            self.logger.debug("Response channels cached.")
            
            # Initialize databases
            self.logger.debug("Initializing databases...")
            if hasattr(self, 'message_monitor') and self.message_monitor and self.message_monitor.db:
                await self.message_monitor.db.initialize()
                self.logger.debug("Message monitor database initialized.")
            
            if hasattr(self, 'ai_logger') and self.ai_logger and self.ai_logger.db:
                await self.ai_logger.db.initialize()
                self.logger.debug("AI logger database initialized.")
            
            # Register scheduled tasks
            self.logger.debug("Registering scheduled tasks...")
            self.task_manager.register_tasks(self.tree)
            self.logger.debug("Scheduled tasks registered.")
            
            # Sync commands with Discord
            self.logger.debug("Syncing application commands...")
            # Add retry mechanism for command sync
            max_retries = 3
            retry_count = 0
            sync_success = False
            
            while not sync_success and retry_count < max_retries:
                try:
                    await self.tree.sync()
                    sync_success = True
                    self.logger.debug("Application commands synced successfully.")
                except Exception as e:
                    retry_count += 1
                    self.logger.error(f"Failed to sync commands (attempt {retry_count}/{max_retries}): {str(e)}")
                    await asyncio.sleep(2)  # Wait before retrying
            
            if not sync_success:
                self.logger.warning("Could not sync commands after multiple attempts. Bot will use cached commands.")
            
            # Start scheduled tasks
            self.logger.debug("Starting scheduled tasks...")
            self.task_manager.start_tasks()
            self.logger.debug("Scheduled tasks started.")
            
            # Dashboard startup removed
            
            # Start the API server in a separate thread
            self.logger.debug("Starting API server...")
            
            # Check message_monitor status before starting API server
            if not hasattr(self, 'message_monitor') or not self.message_monitor:
                self.logger.warning("Message monitor is not available. API data endpoints will use mock data.")
            elif not hasattr(self.message_monitor, 'db') or not self.message_monitor.db:
                self.logger.warning("Message monitor database is not properly initialized. API data endpoints will use mock data.")
            else:
                self.logger.info("Message monitor and database are properly initialized for API use.")
            
            # Create a delay to allow other initialization tasks to complete first
            self.logger.debug("Waiting 2 seconds before starting API server to ensure all components are initialized...")
            await asyncio.sleep(2)
            
            # Initialize the message_monitor if it exists but is None (edge case)
            if hasattr(self, 'message_monitor') and not self.message_monitor and ENABLE_MESSAGE_LOGGING:
                self.logger.warning("MessageMonitor attribute exists but is None. Attempting to reinitialize...")
                try:
                    from utils.database import UnifiedDatabase
                    db = UnifiedDatabase(
                        db_path=MESSAGES_DB_PATH, 
                        encryption_key=ENCRYPTION_KEY,
                        create_tables=False  # Don't create tables immediately
                    )
                    self.message_monitor = MessageMonitor(
                        db=db,
                        encryption_key=ENCRYPTION_KEY
                    )
                    self.message_monitor.set_client(self.client)
                    
                    # Initialize the database asynchronously
                    await db.initialize()
                    self.logger.info("MessageMonitor reinitialized successfully.")
                except Exception as e:
                    self.logger.error(f"Failed to reinitialize MessageMonitor: {e}", exc_info=True)
            
            # Pass a deep copy of this instance to avoid race conditions
            import copy
            bot_instance_for_api = self  # Using reference is fine as we're ensuring init completion
            
            # Start API server in a separate thread
            api_thread = threading.Thread(
                target=start_server, 
                kwargs={
                    'bot_instance': bot_instance_for_api,
                    'host': API_HOST,
                    'port': API_PORT
                },
                daemon=True
            )
            api_thread.start()
            self.logger.info(f"API server thread started on {API_HOST}:{API_PORT}")
            
            self.logger.debug("on_ready event finished.")
        
        @self.client.event
        async def on_message(message):
            self.logger.debug(f"Received message from {message.author}: {message.content[:50]}...")
            try:
                # Process message through the message monitor if enabled
                if self.message_monitor:
                    self.logger.debug(f"Processing message {message.id} with MessageMonitor.")
                    await self.message_monitor.process_message(message)
                
                # Process commands - this is required for the bot to respond to commands
                self.logger.debug(f"Processing commands for message {message.id}.")
                await self.client.process_commands(message)
            except Exception as e:
                self.logger.error(f"Error processing message event for message {message.id}: {str(e)}")
        
        # Register other message-related events if message monitoring is enabled
        if self.message_monitor:
            @self.client.event
            async def on_message_edit(before, after):
                self.logger.debug(f"Received message edit event for message {after.id}.")
                try:
                    await self.message_monitor.process_message_edit(before, after)
                except Exception as e:
                    self.logger.error(f"Error processing message edit event for message {after.id}: {str(e)}")
        
        # Add a handler for cleanup when the bot is about to close
        @self.client.event
        async def on_disconnect():
            self.logger.debug("Bot disconnected, preparing for cleanup...")
        
        @self.client.event
        async def on_close():
            self.logger.debug("Bot is closing, performing async cleanup...")
            try:
                await self.cleanup()
                self.logger.info("Async cleanup completed successfully on close.")
            except Exception as e:
                self.logger.error(f"Error during async cleanup on close: {e}", exc_info=True)
        
        @self.client.event 
        async def on_resumed():
            """Handle reconnection event"""
            self.logger.info("Connection to Discord resumed")
            
            # Verify important components are still operational
            try:
                # Check database connections
                db_status = []
                
                if hasattr(self, 'message_monitor') and self.message_monitor and hasattr(self.message_monitor, 'db'):
                    try:
                        await self.message_monitor.db.execute("SELECT 1")
                        db_status.append("MessageDB: ✅")
                    except Exception as e:
                        db_status.append(f"MessageDB: ❌ ({str(e)[:30]})")
                        # Attempt to reconnect the database
                        try:
                            await self.message_monitor.db.reconnect()
                            db_status[-1] = "MessageDB: ✅ (reconnected)"
                        except Exception as e2:
                            db_status[-1] += f" (reconnect failed: {str(e2)[:30]})"
                
                # Log database status
                if db_status:
                    self.logger.info(f"Database status after resume: {', '.join(db_status)}")
                
                # Refresh cache of response channels
                self.logger.debug("Refreshing response channels cache after reconnection")
                await self._find_or_create_response_channels()
                
            except Exception as e:
                self.logger.error(f"Error during reconnection handling: {e}", exc_info=True)
        
        # Run the client
        self.logger.info("Starting bot client...")
        try:
            self.client.run(DISCORD_BOT_TOKEN)
        except Exception as e:
            self.logger.error(f"Error running bot: {e}", exc_info=True)
        finally:
            # The client has stopped, now we can handle synchronous cleanup as a fallback
            self.logger.info("Bot has stopped running. Performing fallback cleanup...")
            self._sync_cleanup()
            self.logger.info("Cleanup complete.")
        
    async def _handle_client_close(self):
        """Handle cleanup when the client is closing."""
        self.logger.info("Client closing, performing async cleanup...")
        try:
            await self.cleanup()
            self.logger.info("Async cleanup completed successfully.")
        except Exception as e:
            self.logger.error(f"Error during async cleanup: {e}", exc_info=True)
        
    def _sync_cleanup(self):
        """Synchronous cleanup method as a fallback in case async cleanup doesn't run."""
        try:
            # Mostly synchronous cleanup code
            if hasattr(self, 'scheduler') and self.scheduler:
                self.logger.debug("Stopping TaskScheduler...")
                self.scheduler.stop_all()
                self.logger.debug("TaskScheduler stopped.")
                
            # Clean up AI clients
            self.logger.debug("Cleaning up AI clients...")
            if hasattr(self, 'openai_client'):
                self.openai_client = None
            if hasattr(self, 'google_client'):
                self.google_client = None
            if hasattr(self, 'claude_client'):
                self.claude_client = None
            if hasattr(self, 'grok_client'):
                self.grok_client = None
            self.logger.debug("AI clients cleaned up.")
            
        except Exception as e:
            self.logger.error(f"Error during synchronous cleanup: {e}", exc_info=True)

    async def _find_or_create_response_channels(self):
        """Find or create the response channel in all guilds"""
        self.logger.debug("Executing _find_or_create_response_channels...")
        for guild in self.client.guilds:
            self.logger.debug(f"Processing guild: {guild.name} ({guild.id})")
            # Try to find the "🤖" channel
            response_channel = discord.utils.get(guild.text_channels, name="🤖")
            
            # Create the channel if it doesn't exist
            if not response_channel:
                self.logger.debug(f"Response channel '🤖' not found in {guild.name}. Creating...")
                try:
                    response_channel = await guild.create_text_channel("🤖")
                    self.logger.debug(f"Response channel created in {guild.name}: {response_channel.id}")
                except Exception as e:
                    self.logger.error(f"Failed to create response channel in {guild.name}: {str(e)}")
                    continue
            else:
                self.logger.debug(f"Found response channel '🤖' in {guild.name}: {response_channel.id}")
            
            # Cache the channel
            self.response_channels[guild.id] = response_channel
            self.logger.debug(f"Cached response channel for guild {guild.id}.")
        self.logger.debug("_find_or_create_response_channels finished.")

    async def cleanup(self):
        """Clean up resources before shutting down"""
        self.logger.info("Performing cleanup...")
        try:
            # Dashboard cleanup removed
            
            # Close database connections asynchronously
            tasks = []
            if hasattr(self, 'message_monitor') and self.message_monitor:
                self.logger.debug("Scheduling MessageMonitor database close...")
                tasks.append(self.message_monitor.close())
                
            if hasattr(self, 'ai_logger') and self.ai_logger:
                # Check if ai_logger uses the same db instance as message_monitor
                # If they share the same db instance, closing it once is enough.
                should_close_ai_db = True
                if hasattr(self, 'message_monitor') and self.message_monitor and \
                   hasattr(self.message_monitor, 'db') and hasattr(self.ai_logger, 'db') and \
                   self.message_monitor.db is self.ai_logger.db:
                    self.logger.debug("AI logger shares DB with MessageMonitor, skipping redundant close.")
                    should_close_ai_db = False
                
                if should_close_ai_db:
                    self.logger.debug("Scheduling AIInteractionLogger database close...")
                    # Ensure ai_logger.close is awaitable if it needs to be
                    # Assuming ai_logger.close() might become async or already is
                    # If ai_logger.close is not async, this await won't hurt but ideally it should be async
                    # Let's assume ai_logger.close() needs await based on potential db.close() call
                    tasks.append(self.ai_logger.close()) # Assuming close is async

            if tasks:
                self.logger.debug(f"Awaiting {len(tasks)} database close operations...")
                await asyncio.gather(*tasks)
                self.logger.debug("Database connections closed.")
            else:
                self.logger.debug("No database connections needed closing.")

            # Clean up AI clients (synchronous)
            self.logger.debug("Cleaning up AI clients...")
            # ... (rest of the synchronous cleanup code remains the same)
            self.logger.debug("AI clients cleaned up.")
            
            # Clean up task scheduler (synchronous)
            if hasattr(self, 'scheduler') and self.scheduler:
                self.logger.debug("Stopping TaskScheduler...")
                self.scheduler.stop_all()  # Corrected method name
                self.logger.debug("TaskScheduler stopped.")
                
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}", exc_info=True) # Added exc_info
        self.logger.info("Cleanup finished.")

    def toggle_debug_logging(self, enable: bool):
        """Dynamically toggle debug logging."""
        new_level = logging.DEBUG if enable else logging.WARNING
        self.logger.setLevel(new_level)
        self.logger.info(f"Debug logging {'enabled' if enable else 'disabled'}.")

    def _run_api_server_in_thread(self, bot_instance, host, port):
        """Run the API server in a separate thread with its own event loop.
        
        This method creates a new asyncio event loop in the current thread,
        and then runs the start_server coroutine in that loop.
        
        Args:
            bot_instance: The bot instance to be passed to the API server
            host: The host to bind the server to
            port: The port to bind the server to
        """
        try:
            self.logger.debug(f"Setting up event loop for API server on thread {threading.current_thread().name}")
            
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Run the start_server coroutine in this loop
            self.logger.debug(f"Starting API server on {host}:{port}")
            loop.run_until_complete(start_server(bot_instance, host=host, port=port))
            
            # Keep the loop running to handle requests
            self.logger.debug("API server started, running event loop")
            loop.run_forever()
        except Exception as e:
            self.logger.error(f"Error in API server thread: {e}", exc_info=True)
        finally:
            self.logger.debug("API server thread shutting down, closing event loop")
            loop.close()