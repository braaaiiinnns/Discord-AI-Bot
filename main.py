#!/usr/bin/env python3
# Main entry point for the Discord bot application.
# This script imports and runs the actual bot application from the app module.

import sys
import os
import logging

# Ensure we can import from our project directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the config file initialization function
from tools.init_config_files import init_config_files

# Import the bot class
from app.discord.bot import DiscordBot

if __name__ == "__main__":
    # Initialize configuration files - this will delete directories that should be JSON files
    print("Initializing configuration files...")
    init_config_files()
    
    # Start Discord bot in the main thread
    bot = None
    try:
        print("Initializing bot...")
        bot = DiscordBot()
        print("Running bot...")
        # bot.run() is blocking and will handle cleanup internally
        bot.run()
        print("Bot execution finished.")
    except KeyboardInterrupt:
        print("\nBot shutting down via KeyboardInterrupt...")
    except Exception as e:
        print(f"Error during bot execution: {e}")
        logging.exception("Error during bot execution:")
