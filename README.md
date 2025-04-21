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
3. Run the pre-docker script to prepare your local configuration files:
   ```bash
   ./pre-docker.sh
   ```
4. (Optional) Edit the configuration files in the `./data` directory as needed
5. Build and start the Docker container:
   ```bash
   docker-compose up -d --build
   ```
6. To view the logs:
   ```bash
   docker-compose logs -f
   ```
7. To stop the bot:
   ```bash
   docker-compose down
   ```

Data Persistence:
- All bot data is stored in volumes and persisted in your local `./data` directory
- This ensures your data persists across container restarts and updates
- To completely reset data, you can remove the local data directory:
  ```bash
  rm -rf ./data
  ```

## Configuration Files

The bot uses several JSON configuration files stored in the `/data` directory:

- `tasks.json`: Stores scheduled tasks
- `premium_roles.json`: Defines premium roles for servers
- `message_listeners.json`: Contains message trigger configurations
- `previous_role_colors.json`: Stores role color history
- `role_color_cycles.json`: Defines role color cycling configurations

### Docker Configuration

When running in Docker:
1. If these files exist in your local `/data` directory, they will be used
2. If they don't exist, empty default structures will be created automatically
3. Any changes made to these files will persist between container restarts

This approach allows you to keep default configurations in version control while ensuring no sensitive data is included in your repository.
