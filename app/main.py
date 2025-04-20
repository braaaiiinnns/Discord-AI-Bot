"""
Main entry point for the Discord bot application when run from the app package.
This script imports and runs the actual bot application.
"""

import sys
import os
import logging

# Ensure we can import from the project directory one level up
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import the bot class
from app.discord.bot import DiscordBot

# Get a logger instance
logger = logging.getLogger(__name__) 

def main():
    logger.debug("Starting main function...") # Add debug log
    # Create and run the Discord bot
    bot = None
    try:
        logger.debug("Initializing DiscordBot...") # Add debug log
        bot = DiscordBot()
        logger.debug("DiscordBot initialized. Starting run...") # Add debug log
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot shutting down due to KeyboardInterrupt...") # Keep as info
        print("Bot shutting down...")
    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True) # Keep as error
        print(f"Error starting bot: {e}")
    finally:
        # Clean up resources if bot was initialized
        if bot is not None:
            logger.debug("Initiating bot cleanup...") # Add debug log
            try:
                bot.cleanup()
                logger.info("Bot cleanup finished.") # Keep as info
            except Exception as e:
                logger.error(f"Error during cleanup: {e}", exc_info=True) # Keep as error
                print(f"Error during cleanup: {e}")
        else:
            logger.debug("Bot was not initialized, no cleanup needed.") # Add debug log
    logger.debug("Main function finished.") # Add debug log

if __name__ == "__main__":
    # Basic logging config for startup issues before the main logger is set up
    logging.basicConfig(level=logging.INFO) 
    logger.debug("Running as main script.") # Add debug log
    main()