import os
import socket
import logging
from flask import Flask
from waitress import serve
from .app import app, initialize_with_bot
import time

# Set up logger
logger = logging.getLogger('discord_bot.api.server')

# Check if port is already in use
def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def start_server(bot_instance, host='0.0.0.0', port=5000):
    """
    Start the API server with the given bot instance.
    
    Args:
        bot_instance: The bot instance
        host: The host to bind to
        port: The port to bind to
    """
    logger.info("API server initialization beginning...")
    
    try:
        # Validate bot_instance
        if not bot_instance:
            logger.error("Bot instance is None. Cannot initialize API server.")
            return None
            
        # Log bot instance details for diagnostics
        message_monitor_available = False
        database_available = False
        
        if hasattr(bot_instance, 'message_monitor'):
            logger.info("Bot instance has message_monitor attribute.")
            if bot_instance.message_monitor:
                logger.info("MessageMonitor object is available.")
                message_monitor_available = True
                if hasattr(bot_instance.message_monitor, 'db'):
                    logger.info("MessageMonitor has database attribute.")
                    if bot_instance.message_monitor.db:
                        logger.info("Database object is available.")
                        database_available = True
                    else:
                        logger.warning("Database object is None.")
                else:
                    logger.warning("MessageMonitor does not have database attribute.")
            else:
                logger.warning("MessageMonitor object is None.")
        else:
            logger.warning("Bot instance does not have message_monitor attribute.")
        
        # Provide a summary of component availability
        logger.info(f"Component status - MessageMonitor: {'✅' if message_monitor_available else '❌'}, Database: {'✅' if database_available else '❌'}")
        
        # Add a small delay to ensure all components have stabilized
        logger.info("Waiting 1 second for all components to stabilize...")
        time.sleep(1)
            
        # Initialize the API with the bot instance
        logger.info("Initializing API with bot instance...")
        initialize_with_bot(bot_instance)
        logger.info("API server initialized with bot instance.")
        
        # Check if port is already in use and increment if needed
        while is_port_in_use(port):
            logger.warning(f"Port {port} is already in use, trying {port+1}")
            port += 1
        
        # Start the Flask app with proper host and debug settings
        logger.info(f"Starting API server on {host}:{port}")
        try:
            logger.info("API server is now running and handling requests")
            serve(app, host=host, port=port, threads=8)
        except OSError as e:
            if "Address already in use" in str(e):
                logger.warning(f"Port {port} is already in use. Trying port {port + 1}.")
                try:
                    serve(app, host=host, port=port + 1, threads=8)
                    logger.info(f"API server started on {host}:{port + 1}")
                except Exception as e_inner:
                    logger.error(f"Failed to start API server on fallback port {port + 1}: {e_inner}", exc_info=True)
            else:
                logger.error(f"Failed to start API server: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"An unexpected error occurred while starting the API server: {e}", exc_info=True)
    
    except Exception as e:
        logger.error(f"Error starting API server: {e}", exc_info=True)
        return None

# Main entry point if run directly
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    start_server(port=port)