import os
from flask import Flask
from flask_cors import CORS
import logging

# Removed import of APIAuthManager

# Set up logger
logger = logging.getLogger('discord_bot.api')

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'default_secret_key_for_development')

# Enable CORS
CORS(app, supports_credentials=True) # supports_credentials might not be needed without session cookies

# Removed initialization of APIAuthManager and registration of its blueprint

# Import blueprints
try:
    from .dashboard_api import dashboard_bp
    
    # Register blueprints
    app.register_blueprint(dashboard_bp)
    # Removed registration of auth_manager.bp
    
    logger.info("Flask application initialized successfully with API blueprints")
except Exception as e:
    logger.error(f"Error initializing Flask application: {str(e)}", exc_info=True)

# Store reference to the bot instance for API use
bot_instance_ref = None

def initialize_with_bot(bot_instance):
    """Initialize the API with a reference to the bot instance"""
    global bot_instance_ref
    bot_instance_ref = bot_instance
    
    # Store the bot instance in app config for easy access in routes
    app.config['BOT_INSTANCE'] = bot_instance
    
    # Add multiple attempts for message_monitor access
    max_retries = 3
    retry_delay = 1  # seconds
    
    # Store the data service (ensure proper message_monitor access)
    db_connection = None
    success = False
    
    for attempt in range(max_retries):
        try:
            if bot_instance and hasattr(bot_instance, 'message_monitor') and bot_instance.message_monitor:
                logger.info(f"Attempt {attempt+1}/{max_retries}: Message monitor found on bot instance. Accessing database...")
                db_connection = bot_instance.message_monitor.get_database()
                
                if db_connection:
                    logger.info("Successfully obtained database connection from message_monitor.")
                    app.config['DATA_SERVICE'] = db_connection
                    success = True
                    break
                else:
                    logger.warning(f"Attempt {attempt+1}/{max_retries}: Database connection is None.")
            else:
                logger.warning(f"Attempt {attempt+1}/{max_retries}: Message monitor not available.")
            
            # Wait before retrying
            if attempt < max_retries - 1:
                logger.info(f"Waiting {retry_delay} seconds before next attempt...")
                import time
                time.sleep(retry_delay)
        except Exception as e:
            logger.error(f"Error during attempt {attempt+1}/{max_retries} to access database: {e}", exc_info=True)
            if attempt < max_retries - 1:
                logger.info(f"Waiting {retry_delay} seconds before next attempt...")
                import time
                time.sleep(retry_delay)
    
    if not success:
        # Log detailed diagnostic information
        if not bot_instance:
            logger.warning("Bot instance is None. Data service not initialized.")
        elif not hasattr(bot_instance, 'message_monitor'):
            logger.warning("Bot instance does not have message_monitor attribute. Data service not initialized.")
        elif not bot_instance.message_monitor:
            logger.warning("Bot instance has message_monitor attribute but it's None. Data service not initialized.")
        else:
            logger.warning("Message monitor exists but database access failed after multiple attempts.")
        
        app.config['DATA_SERVICE'] = None
        logger.warning("Data service not initialized. API endpoints will use mock data.")

    # Initialize dashboard API (passing the full bot instance now)
    from .dashboard_api import initialize
    # Since initialize is now an async function, we need to run it in an event loop
    import asyncio
    try:
        # Create a new event loop for this thread if needed
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # If there is no event loop in this thread, create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Run the initialize function in the event loop
        loop.run_until_complete(initialize(bot_instance))
        logger.info("Successfully initialized dashboard API asynchronously")
    except Exception as e:
        logger.error(f"Error initializing dashboard API: {e}", exc_info=True)
    
    logger.info(f"API initialized with bot reference. Data service available: {success}")