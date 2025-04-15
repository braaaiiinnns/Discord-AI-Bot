#!/usr/bin/env python3
# Main entry point for the Discord bot application.
# This script imports and runs the actual bot application from the app module.

import sys
import os

# Ensure we can import from our project directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
    finally:
        # Clean up resources if bot was initialized
        if bot is not None:
            bot.cleanup()

if __name__ == "__main__":
    main()
