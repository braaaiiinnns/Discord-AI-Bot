import os
import tempfile
from config.base import BASE_DATA_DIRECTORY

# API configuration
API_HOST = os.getenv('API_HOST', '127.0.0.1')
API_PORT = int(os.getenv('API_PORT', '5000'))

# Dashboard configuration
ENABLE_DASHBOARD = True
DASHBOARD_HOST = os.getenv('DASHBOARD_HOST', '127.0.0.1')
DASHBOARD_PORT = int(os.getenv('DASHBOARD_PORT', '8050'))

# Flask session directory
FLASK_SESSION_DIR = os.path.join(BASE_DATA_DIRECTORY, 'flask_session')

# Define the directory for session files if not already set
if not os.environ.get('FLASK_SESSION_DIR'):
    FLASK_SESSION_DIR = os.path.join(tempfile.gettempdir(), 'discord_bot_sessions')

# Discord OAuth for Dashboard
DISCORD_CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
DISCORD_REDIRECT_URI = os.getenv('DISCORD_REDIRECT_URI', f'http://{DASHBOARD_HOST}:{DASHBOARD_PORT}/callback')
DASHBOARD_REQUIRE_LOGIN = os.getenv('DASHBOARD_REQUIRE_LOGIN', 'true').lower() == 'true'