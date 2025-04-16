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
