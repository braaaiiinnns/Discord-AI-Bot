import os
import json
import requests
import secrets
import logging
from flask import Flask, redirect, url_for, session, request, Blueprint
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from urllib.parse import urlencode
from datetime import datetime, timedelta

logger = logging.getLogger('discord_bot.dashboard.auth')

# Discord OAuth2 constants
DISCORD_CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
DISCORD_REDIRECT_URI = os.getenv('DISCORD_REDIRECT_URI', 'http://localhost:8050/callback')
DISCORD_API_ENDPOINT = 'https://discord.com/api/v10'  # Using v10 API endpoint

# OAuth2 endpoints
DISCORD_AUTH_URL = f'{DISCORD_API_ENDPOINT}/oauth2/authorize'
DISCORD_TOKEN_URL = f'{DISCORD_API_ENDPOINT}/oauth2/token'

class DashboardUser(UserMixin):
    """User class for Flask-Login"""
    
    def __init__(self, user_id, username, discriminator=None, avatar=None, guilds=None):
        self.id = user_id
        self.username = username
        self.discriminator = discriminator
        self.avatar = avatar
        self.guilds = guilds or []
        self.authenticated = True
        self.created_at = datetime.now()
    
    def to_dict(self):
        """Convert user to dictionary for storage"""
        return {
            'id': self.id,
            'username': self.username,
            'discriminator': self.discriminator,
            'avatar': self.avatar,
            'guilds': self.guilds,
            'created_at': self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create user from dictionary"""
        user = cls(
            user_id=data['id'],
            username=data['username'],
            discriminator=data.get('discriminator'),
            avatar=data.get('avatar'),
            guilds=data.get('guilds', [])
        )
        if 'created_at' in data:
            user.created_at = datetime.fromisoformat(data['created_at'])
        return user
    
    def is_member_of_guild(self, guild_id):
        """Check if user is a member of a specific guild"""
        return str(guild_id) in [str(g.get('id')) for g in self.guilds]
    
    def get_avatar_url(self):
        """Get the user's avatar URL"""
        if not self.avatar:
            return "https://cdn.discordapp.com/embed/avatars/0.png"
        
        # Discord now uses different CDN URL format
        return f"https://cdn.discordapp.com/avatars/{self.id}/{self.avatar}.png"
    
    def get_display_name(self):
        """Get the user's display name"""
        # Discord has removed discriminators in newer API versions
        if self.discriminator and self.discriminator != '0':
            return f"{self.username}#{self.discriminator}"
        return self.username
        
class DiscordAuthManager:
    """Manager for Discord OAuth2 authentication"""
    
    def __init__(self, app, bot_client=None, login_callback=None):
        """
        Initialize the Discord authentication manager.
        
        Args:
            app (Flask): The Flask application
            bot_client: Optional Discord bot client for fetching additional data
            login_callback: Optional callback to run after successful login
        """
        self.app = app
        self.bot_client = bot_client
        self.login_callback = login_callback
        
        # Setup login manager
        self.login_manager = LoginManager()
        self.login_manager.init_app(app)
        self.login_manager.login_view = "auth.login"
        
        # Create users cache
        self.users = {}
        
        # Verify configuration
        self._check_configuration()
        
        # Register user loader
        @self.login_manager.user_loader
        def load_user(user_id):
            return self.users.get(user_id)
        
        # Create auth routes
        self.bp = self._create_routes()
        
        logger.info("Discord auth manager initialized")
    
    def _check_configuration(self):
        """Check if Discord OAuth2 is properly configured"""
        if not DISCORD_CLIENT_ID:
            logger.warning("DISCORD_CLIENT_ID not set. Discord authentication will not work.")
        
        if not DISCORD_CLIENT_SECRET:
            logger.warning("DISCORD_CLIENT_SECRET not set. Discord authentication will not work.")
        
        if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET:
            logger.warning("Discord authentication is not properly configured. Set DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET.")
        else:
            logger.info(f"Discord OAuth2 configured with redirect URI: {DISCORD_REDIRECT_URI}")
    
    def _create_routes(self):
        """Create the authentication routes"""
        auth_bp = Blueprint('auth', __name__)
        
        @auth_bp.route('/login')
        def login():
            """Redirect user to Discord OAuth2 login"""
            # Generate state for security
            state = secrets.token_hex(16)
            session['oauth2_state'] = state
            
            # Build the authorization URL
            params = {
                'client_id': DISCORD_CLIENT_ID,
                'redirect_uri': DISCORD_REDIRECT_URI,
                'response_type': 'code',
                'scope': 'identify guilds',
                'state': state,
                'prompt': 'none'  # Don't prompt if already authorized
            }
            
            auth_url = f"{DISCORD_AUTH_URL}?{urlencode(params)}"
            return redirect(auth_url)
        
        @auth_bp.route('/logout')
        @login_required
        def logout():
            """Log out the user"""
            user_id = current_user.id
            logout_user()
            if user_id in self.users:
                del self.users[user_id]
            
            return redirect(url_for('index'))
        
        @auth_bp.route('/callback')
        def callback():
            """Handle the OAuth2 callback from Discord"""
            # Verify state for security
            state = request.args.get('state')
            saved_state = session.get('oauth2_state')
            logger.debug(f"Callback received with state: {state}, code: {request.args.get('code')}")
            logger.debug(f"Session state: {saved_state}")
            
            if not state or state != saved_state:
                logger.warning("OAuth2 state mismatch")
                return redirect(url_for('auth.login'))
            
            # Exchange authorization code for token
            code = request.args.get('code')
            if not code:
                logger.warning("No authorization code received from Discord")
                return redirect(url_for('auth.login'))
            
            # Request access token
            token_data = {
                'client_id': DISCORD_CLIENT_ID,
                'client_secret': DISCORD_CLIENT_SECRET,
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': DISCORD_REDIRECT_URI
            }
            
            try:
                # Using the requests library with timeouts for robustness
                token_response = requests.post(
                    DISCORD_TOKEN_URL, 
                    data=token_data, 
                    timeout=10,
                    headers={'Content-Type': 'application/x-www-form-urlencoded'}
                )
                logger.debug(f"Token response status: {token_response.status_code}, body: {token_response.text}")
                token_response.raise_for_status()
                token_json = token_response.json()
                access_token = token_json.get('access_token')
                
                if not access_token:
                    logger.error("Failed to get access token")
                    return redirect(url_for('auth.login'))
                
                # Fetch user data from Discord
                user_data = self._fetch_user_data(access_token)
                guilds_data = self._fetch_user_guilds(access_token)
                
                if not user_data:
                    logger.error("Failed to get user data")
                    return redirect(url_for('auth.login'))
                
                # Create user object
                user = DashboardUser(
                    user_id=user_data['id'],
                    username=user_data['username'],
                    discriminator=user_data.get('discriminator'),
                    avatar=user_data.get('avatar'),
                    guilds=guilds_data
                )
                
                # Cache the user
                self.users[user.id] = user
                
                # Login the user
                login_user(user)
                
                # Run optional login callback
                if self.login_callback:
                    self.login_callback(user)
                
                logger.info(f"User {user.username} (ID: {user.id}) logged in")
                
                # Redirect to next or index
                next_url = request.args.get('next') or url_for('index')
                return redirect(next_url)
                
            except requests.RequestException as e:
                logger.error(f"Error during OAuth2 token exchange: {e}")
                return redirect(url_for('auth.login'))
        
        return auth_bp
    
    def _fetch_user_data(self, access_token):
        """Fetch user data from Discord API"""
        try:
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            response = requests.get(
                f'{DISCORD_API_ENDPOINT}/users/@me', 
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Error fetching user data: {e}")
            return None
    
    def _fetch_user_guilds(self, access_token):
        """Fetch user's guilds from Discord API"""
        try:
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            response = requests.get(
                f'{DISCORD_API_ENDPOINT}/users/@me/guilds', 
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Error fetching user guilds: {e}")
            return []
    
    def require_guild_member(self, guild_id):
        """Decorator to require user to be a member of a specific guild"""
        def decorator(f):
            @login_required
            def decorated_function(*args, **kwargs):
                if not current_user.is_member_of_guild(guild_id):
                    return redirect(url_for('auth.login'))
                return f(*args, **kwargs)
            return decorated_function
        return decorator