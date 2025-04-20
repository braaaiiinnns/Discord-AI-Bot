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
    # Store the data service (assuming it's still needed from message_monitor)
    if hasattr(bot_instance, 'message_monitor') and bot_instance.message_monitor:
        app.config['DATA_SERVICE'] = bot_instance.message_monitor.get_database()
    else:
        app.config['DATA_SERVICE'] = None
        logger.warning("Message monitor not found on bot instance. Data service not initialized.")

    # Initialize dashboard API (passing the full bot instance now)
    from .dashboard_api import initialize
    initialize(bot_instance)
    
    logger.info("API initialized with bot reference")