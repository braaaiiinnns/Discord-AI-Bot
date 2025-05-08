"""
Authentication middleware for API security.
Provides both API key authentication and user session authentication.
"""

import os
import asyncio  # Ensuring asyncio is properly imported
import secrets
import time
from functools import wraps
from quart import request, jsonify, current_app, redirect, session, abort
import logging
import hashlib
import hmac

# Import the API key and OAuth2 configuration from config
from config.base import API_SECRET_KEY
from config.bot_config import DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, DISCORD_REDIRECT_URI
from .user_model import user_manager

# Set up logger
logger = logging.getLogger('discord_bot.api.auth')

# Discord API base URL
DISCORD_API_BASE_URL = 'https://discord.com/api/v10'
DISCORD_AUTH_URL = f'{DISCORD_API_BASE_URL}/oauth2/authorize'

# Security improvement: CSRF token generation and validation
def generate_csrf_token():
    """Generate a secure CSRF token"""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']

def validate_csrf_token(token):
    """Validate a CSRF token against the one stored in the session"""
    if not token or not session.get('csrf_token'):
        return False
    # Security improvement: Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(token, session.get('csrf_token'))

# Security improvement: Rate limiting helpers
request_history = {}

def is_rate_limited(key, limit=60, period=60):
    """
    Basic rate limiting implementation
    
    Args:
        key: Identifier for the client (IP address, API key, etc.)
        limit: Maximum number of requests allowed in the period
        period: Time period in seconds
    
    Returns:
        Boolean indicating if the request should be rate limited
    """
    now = time.time()
    if key not in request_history:
        request_history[key] = []
    
    # Clean up old requests
    request_history[key] = [timestamp for timestamp in request_history[key] if now - timestamp < period]
    
    # Check if limit exceeded
    if len(request_history[key]) >= limit:
        return True
    
    # Add current request
    request_history[key].append(now)
    return False

def get_client_identifier():
    """Get a unique identifier for the client (IP + user agent)"""
    ip = request.remote_addr
    agent = request.headers.get('User-Agent', '')
    identifier = f"{ip}:{hashlib.md5(agent.encode()).hexdigest()}"
    return identifier

def require_api_key(f):
    """Decorator to require a valid API key for an endpoint."""
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        # Security improvement: Rate limiting
        client_id = get_client_identifier()
        if is_rate_limited(client_id, limit=100, period=60):  # 100 requests per minute
            logger.warning(f"Rate limit exceeded for {client_id}")
            return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429
            
        api_key = None
        # Check for API key in 'Authorization: Bearer <key>' header
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                api_key = auth_header.split(' ', 1)[1]
        # Fallback: Check for API key in 'X-API-Key' header
        elif 'X-API-Key' in request.headers:
            api_key = request.headers['X-API-Key']

        if not api_key:
            logger.warning("API key missing from request")
            # Security improvement: Add delay to prevent timing attacks
            await asyncio.sleep(0.5)
            return jsonify({"error": "API key required"}), 401

        # Security improvement: Rate limiting by API key
        if is_rate_limited(f"api_key:{api_key}", limit=200, period=60):  # 200 requests per minute per API key
            logger.warning(f"API key rate limit exceeded")
            return jsonify({"error": "API key rate limit exceeded. Please try again later."}), 429

        # First check if this is a valid user API key
        user = await user_manager.get_user_by_api_key(api_key)
        if user:
            # Valid user API key, proceed with the original function
            # Add the user to the kwargs so the endpoint can access it
            kwargs['user'] = user
            # Security improvement: Log access for audit trail
            logger.info(f"API access by user {user['id']} to {request.path}")
            if asyncio.iscoroutinefunction(f):
                return await f(*args, **kwargs)
            else:
                return f(*args, **kwargs)

        # If not a user API key, check if it's the global API key
        if not API_SECRET_KEY or api_key != API_SECRET_KEY:
            # Security improvement: Add delay to prevent timing attacks
            await asyncio.sleep(0.5)
            logger.warning("Invalid API key provided")
            return jsonify({"error": "Invalid API key"}), 403

        # If key is valid, proceed with the original function
        # Security improvement: Log access for audit trail
        logger.info(f"API access with master key to {request.path}")
        if asyncio.iscoroutinefunction(f):
            return await f(*args, **kwargs)
        else:
            return f(*args, **kwargs)
            
    return decorated_function

def require_auth(f):
    """Decorator to require user authentication (session) for an endpoint."""
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        # Security improvement: Rate limiting
        client_id = get_client_identifier()
        if is_rate_limited(client_id, limit=60, period=60):  # 60 requests per minute
            logger.warning(f"Rate limit exceeded for {client_id}")
            return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429
            
        session_id = request.cookies.get('session_id')
        if not session_id:
            logger.warning("No session ID in request")
            # Security improvement: Add delay to prevent timing attacks
            await asyncio.sleep(0.5)
            return jsonify({"error": "Authentication required"}), 401
        
        user = await user_manager.get_user_by_session(session_id)
        if not user:
            logger.warning("Invalid or expired session")
            # Security improvement: Add delay to prevent timing attacks
            await asyncio.sleep(0.5)
            return jsonify({"error": "Invalid or expired session"}), 401
        
        # Add the user to the kwargs so the endpoint can access it
        kwargs['user'] = user
        
        # Security improvement: Log access for audit trail
        logger.info(f"Authenticated access by user {user['id']} to {request.path}")
        
        # If authenticated, proceed with the original function
        if asyncio.iscoroutinefunction(f):
            return await f(*args, **kwargs)
        else:
            return f(*args, **kwargs)
    
    return decorated_function

def require_csrf(f):
    """Decorator to require valid CSRF token for an endpoint."""
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        # Only apply to mutating methods
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            token = None
            
            # Check for token in request
            if request.is_json:
                token = request.json.get('csrf_token')
            elif request.form:
                token = request.form.get('csrf_token')
            else:
                token = request.headers.get('X-CSRF-Token')
            
            # Validate token
            if not validate_csrf_token(token):
                logger.warning("Invalid or missing CSRF token")
                return jsonify({"error": "Invalid or missing CSRF token"}), 403
                
        # If CSRF check passes or method is safe, proceed with the original function
        if asyncio.iscoroutinefunction(f):
            return await f(*args, **kwargs)
        else:
            return f(*args, **kwargs)
            
    return decorated_function

def require_admin(f):
    """Decorator to require admin privileges for an endpoint."""
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        # Security improvement: Rate limiting for admin endpoints
        client_id = get_client_identifier()
        if is_rate_limited(client_id, limit=30, period=60):  # 30 requests per minute for admin endpoints
            logger.warning(f"Rate limit exceeded for admin endpoint by {client_id}")
            return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429
            
        session_id = request.cookies.get('session_id')
        if not session_id:
            logger.warning("No session ID in admin request")
            # Security improvement: Add delay to prevent timing attacks
            await asyncio.sleep(1.0)  # Longer delay for admin endpoints
            return jsonify({"error": "Authentication required"}), 401
        
        user = await user_manager.get_user_by_session(session_id)
        if not user:
            logger.warning("Invalid or expired session for admin request")
            # Security improvement: Add delay to prevent timing attacks
            await asyncio.sleep(1.0)  # Longer delay for admin endpoints
            return jsonify({"error": "Invalid or expired session"}), 401
        
        if not user.get('is_admin'):
            logger.warning(f"User {user['id']} attempted to access admin endpoint without privileges")
            # Security improvement: Add delay to prevent timing attacks
            await asyncio.sleep(1.0)  # Longer delay for admin endpoints
            return jsonify({"error": "Admin privileges required"}), 403
        
        # Add the user to the kwargs so the endpoint can access it
        kwargs['user'] = user
        
        # Security improvement: Log access for audit trail
        logger.info(f"Admin access by user {user['id']} to {request.path}")
        
        # If authenticated and authorized, proceed with the original function
        if asyncio.iscoroutinefunction(f):
            return await f(*args, **kwargs)
        else:
            return f(*args, **kwargs)
    
    return decorated_function

async def get_authenticated_user():
    """Utility function to get the currently authenticated user."""
    session_id = request.cookies.get('session_id')
    if not session_id:
        return None
        
    return await user_manager.get_user_by_session(session_id)

# Security improvement: More secure token validation
def validate_token(token):
    """
    Validate an access token.
    Improved implementation with better security.
    """
    if not token:
        return False
        
    # Security improvement: Use constant-time comparison
    return hmac.compare_digest(token, API_SECRET_KEY) if API_SECRET_KEY else False

# Security improvement: Add method to sanitize user input
def sanitize_input(input_data):
    """
    Sanitize user input to prevent injection attacks
    
    Args:
        input_data: String input to sanitize
        
    Returns:
        Sanitized string
    """
    if not input_data:
        return input_data
        
    # Basic sanitization - replace dangerous characters
    dangerous_chars = ['<', '>', '"', "'", ';', '(', ')']
    result = str(input_data)
    for char in dangerous_chars:
        result = result.replace(char, '')
    
    return result

# Routes to bridge between client.js and auth_routes.py
async def login():
    """Redirect to the login route in auth_routes.py"""
    logger.info("Redirecting to Discord OAuth login")
    # Security improvement: Generate CSRF token for the session
    generate_csrf_token()
    return redirect('/api/auth/login')

async def logout():
    """Redirect to the logout route in auth_routes.py"""
    logger.info("Redirecting to logout endpoint")
    return redirect('/api/auth/logout')

def get_oauth2_url():
    """Get the Discord OAuth2 authorization URL."""
    # Security improvement: Always include state parameter for CSRF protection
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    
    params = {
        'client_id': DISCORD_CLIENT_ID,
        'redirect_uri': DISCORD_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'identify email',
        'state': state  # Add state for CSRF protection
    }
    
    from urllib.parse import urlencode
    auth_url = f"{DISCORD_AUTH_URL}?{urlencode(params)}"
    return auth_url