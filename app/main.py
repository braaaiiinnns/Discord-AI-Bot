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

def main():
    # Create and run the Discord bot
    bot = None
    try:
        bot = DiscordBot()
        bot.run()
    except KeyboardInterrupt:
        print("Bot shutting down...")
    except Exception as e:
        print(f"Error starting bot: {e}")
        logging.error(f"Error starting bot: {e}", exc_info=True)
    finally:
        # Clean up resources if bot was initialized
        if bot is not None:
            try:
                bot.cleanup()
            except Exception as e:
                print(f"Error during cleanup: {e}")
                logging.error(f"Error during cleanup: {e}", exc_info=True)

if __name__ == "__main__":
    main()