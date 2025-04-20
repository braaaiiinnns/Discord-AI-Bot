# ChatGPT Discord Bot

A Discord bot powered by ChatGPT that provides various capabilities including:
- AI-powered chat responses
- Task scheduling
- Role color management
- Dashboard integration
- And more!

## Project Structure
```
chatgpt_discord_bot/                # Project root
├── README.md                       # Project documentation
├── requirements.txt                # Python dependencies
├── .env                            # Environment configuration (not in git)
├── config/                         # Configuration files/settings
│   ├── __init__.py
│   ├── config.py                   # Bot configuration
│   └── tasks.json                  # Task definitions
├── app/                            # Main application package
│   ├── __init__.py                 # Application initialization
│   ├── main.py                     # Application entry point
│   ├── discord/                    # Discord bot logic
│   │   ├── __init__.py
│   │   ├── bot.py                  # Discord bot initialization
│   │   ├── commands.py             # Discord commands
│   │   ├── message_monitor.py      # Message processing 
│   │   ├── task_scheduler.py       # Scheduled task handling
│   │   ├── role_color_manager.py   # Role color management
│   │   ├── random_ascii_emoji.py   # ASCII emoji functionality
│   │   ├── state.py                # State management
│   │   └── cogs/                   # Command modules
│   │       └── __init__.py
│   └── dashboard/                  # Web dashboard
│       ├── __init__.py
│       ├── routes.py               # Route definitions
│       ├── auth.py                 # Authentication
│       ├── dashboard.py            # Dashboard views
│       ├── static/                 # Static assets
│       └── templates/              # HTML templates
├── utils/                          # Helper modules
│   ├── __init__.py
│   ├── logger.py                   # Logging configuration
│   ├── database.py                 # Database access
│   ├── ai_services.py              # AI integration
│   ├── ai_logger.py                # AI-specific logging
│   ├── ncrypt.py                   # Encryption utilities
│   └── utilities.py                # Miscellaneous utilities
├── data/                           # Data storage
│   ├── files/                      # Static data files
│   │   ├── ascii_emoji.json        # ASCII emoji definitions
│   │   └── task_examples.json      # Example tasks
│   └── *.db                        # Database files
├── tests/                          # Test suite
│   ├── __init__.py
│   └── test_message_monitor.py     # Tests for message_monitor.py
└── logs/                           # Log files
```

## Setup
1. Install requirements: `pip install -r requirements.txt`
2. Configure your .env file with necessary credentials
3. Run the bot: `python -m app.main`

## Docker Deployment
The bot can be easily deployed using Docker for better isolation and persistence:

1. Make sure Docker and Docker Compose are installed on your system
2. Configure your `.env` file with all the necessary credentials:
   ```
   DISCORD_BOT_TOKEN=your_discord_bot_token
   OPENAI_API_KEY=your_openai_api_key
   GOOGLE_GENAI_API_KEY=your_google_api_key
   CLAUDE_API_KEY=your_claude_api_key
   GROK_API_KEY=your_grok_api_key
   ENCRYPTION_KEY=your_encryption_key
   API_SECRET_KEY=your_api_secret_key
   DISCORD_CLIENT_ID=your_discord_client_id
   DISCORD_CLIENT_SECRET=your_discord_client_secret
   DASHBOARD_PORT=8050  # Optional, defaults to 8050
   ```
3. Build and start the Docker container:
   ```bash
   docker-compose up -d --build
   ```
4. To view the logs:
   ```bash
   docker-compose logs -f
   ```
5. To stop the bot:
   ```bash
   docker-compose down
   ```

Data Persistence:
- All bot data is stored in Docker volumes (`discord_bot_data` and `discord_bot_logs`)
- This ensures your data persists across container restarts and updates
- To completely reset data, you can remove the volumes:
  ```bash
  docker-compose down -v
  ```
