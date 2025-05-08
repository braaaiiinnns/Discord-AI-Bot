#!/usr/bin/env python3
# Main entry point for the Discord bot application.
# This script imports and runs the actual bot application from the app module.

import sys
import os
import logging
import argparse
import threading
import time

# Ensure we can import from our project directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the config file initialization function
from tools.init_config_files import init_config_files

# Import the bot class, API server and Dashboard server
from app.discord.bot import DiscordBot
from app.api.server import start_server as start_api_server
from app.dashboard.server import start_dashboard_server

# Import configuration
from config.dashboard_config import DASHBOARD_HOST, DASHBOARD_PORT

def parse_arguments():
    """Parse command line arguments for controlling which components to start"""
    parser = argparse.ArgumentParser(description="Discord Bot with Dashboard")
    parser.add_argument('--bot', action='store_true', help='Start the Discord bot')
    parser.add_argument('--api', action='store_true', help='Start the API server')
    parser.add_argument('--dashboard', action='store_true', help='Start the dashboard server')
    parser.add_argument('--all', action='store_true', help='Start all components (default)')
    parser.add_argument('--api-host', default='0.0.0.0', help='Host for the API server (default: 0.0.0.0)')
    parser.add_argument('--api-port', type=int, default=5000, help='Port for the API server (default: 5000)')
    parser.add_argument('--dashboard-host', default=DASHBOARD_HOST, help=f'Host for the dashboard server (default: {DASHBOARD_HOST})')
    parser.add_argument('--dashboard-port', type=int, default=DASHBOARD_PORT, help=f'Port for the dashboard server (default: {DASHBOARD_PORT})')
    parser.add_argument('--no-browser', action='store_true', help="Don't open browser automatically")
    
    args = parser.parse_args()
    
    # If no arguments provided or --all specified, enable everything
    if len(sys.argv) == 1 or args.all:
        args.bot = True
        args.api = True
        args.dashboard = True
    
    return args

if __name__ == "__main__":
    # Parse command line arguments
    args = parse_arguments()
    
    # Initialize configuration files - this will delete directories that should be JSON files
    print("Initializing configuration files...")
    init_config_files()
    
    # Create a logger for the main script
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger('discord_bot.main')
    
    bot = None
    api_server_thread = None
    dashboard_server_thread = None
    
    try:
        # Start the bot if requested
        if args.bot:
            print("Initializing Discord bot...")
            bot = DiscordBot()
            
            # Start the API server in a separate thread if requested
            if args.api:
                print(f"Starting API server on {args.api_host}:{args.api_port}...")
                api_server_thread = threading.Thread(
                    target=start_api_server,
                    kwargs={
                        'bot_instance': bot,
                        'host': args.api_host,
                        'port': args.api_port
                    },
                    daemon=True  # This ensures the thread exits when the main thread exits
                )
                api_server_thread.start()
                logger.info(f"API server thread started on {args.api_host}:{args.api_port}")
                
                # Give the API server a moment to start up
                time.sleep(1)
            
            # Start the dashboard server in a separate thread if requested
            if args.dashboard:
                print(f"Starting dashboard server on {args.dashboard_host}:{args.dashboard_port}...")
                dashboard_server_thread = threading.Thread(
                    target=start_dashboard_server,
                    kwargs={
                        'host': args.dashboard_host,
                        'port': args.dashboard_port,
                        'open_browser': not args.no_browser
                    },
                    daemon=True  # This ensures the thread exits when the main thread exits
                )
                dashboard_server_thread.start()
                logger.info(f"Dashboard server thread started on {args.dashboard_host}:{args.dashboard_port}")
                
                # Give the dashboard server a moment to start up
                time.sleep(1)
            
            # Run the bot (this is blocking and will handle cleanup internally)
            print("Running Discord bot...")
            bot.run()
            print("Bot execution finished.")
            
        # Start only the API server if bot is not requested but API is
        elif args.api:
            print(f"Starting API server only on {args.api_host}:{args.api_port}...")
            # Create a dummy bot instance with minimal functionality for the API
            from app.discord.state import BotState
            dummy_bot = type('DummyBot', (), {
                'message_monitor': None,
                'ai_logger': None,
                'bot_state': BotState(timeout=3600)
            })
            
            # Start the dashboard server in a separate thread if requested
            if args.dashboard:
                print(f"Starting dashboard server on {args.dashboard_host}:{args.dashboard_port}...")
                dashboard_server_thread = threading.Thread(
                    target=start_dashboard_server,
                    kwargs={
                        'host': args.dashboard_host,
                        'port': args.dashboard_port,
                        'open_browser': not args.no_browser
                    },
                    daemon=True
                )
                dashboard_server_thread.start()
                logger.info(f"Dashboard server thread started on {args.dashboard_host}:{args.dashboard_port}")
            
            # Start the API server in the main thread
            start_api_server(
                bot_instance=dummy_bot,
                host=args.api_host,
                port=args.api_port
            )
        
        # Start only the dashboard server if neither bot nor API is requested
        elif args.dashboard:
            print(f"Starting dashboard server only on {args.dashboard_host}:{args.dashboard_port}...")
            start_dashboard_server(
                host=args.dashboard_host,
                port=args.dashboard_port,
                open_browser=not args.no_browser
            )
    
    except KeyboardInterrupt:
        print("\nApplication shutting down via KeyboardInterrupt...")
    except Exception as e:
        print(f"Error during execution: {e}")
        logging.exception("Error during execution:")
