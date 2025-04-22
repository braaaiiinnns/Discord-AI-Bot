"""
Authentication middleware for API security.
Provides both API key authentication and user session authentication.
"""

import os
import asyncio
from functools import wraps
from quart import request, jsonify, current_app
import logging

# Import the API key from config
from config.config import API_SECRET_KEY
from .user_model import user_manager

# Set up logger
logger = logging.getLogger('discord_bot.api.auth')

def require_api_key(f):
    """Decorator to require a valid API key for an endpoint."""
    @wraps(f)
    async def decorated_function(*args, **kwargs):
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
            return jsonify({"error": "API key required"}), 401

        # First check if this is a valid user API key
        user = await user_manager.get_user_by_api_key(api_key)
        if user:
            # Valid user API key, proceed with the original function
            # Add the user to the kwargs so the endpoint can access it
            kwargs['user'] = user
            if asyncio.iscoroutinefunction(f):
                return await f(*args, **kwargs)
            else:
                return f(*args, **kwargs)

        # If not a user API key, check if it's the global API key
        if api_key != API_SECRET_KEY:
            logger.warning("Invalid API key provided")
            return jsonify({"error": "Invalid API key"}), 403

        # If key is valid, proceed with the original function
        # Handle both async and sync functions
        if asyncio.iscoroutinefunction(f):
            return await f(*args, **kwargs)
        else:
            return f(*args, **kwargs)
            
    return decorated_function

def require_auth(f):
    """Decorator to require user authentication (session) for an endpoint."""
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        session_id = request.cookies.get('discord_session')
        if not session_id:
            logger.warning("No session ID in request")
            return jsonify({"error": "Authentication required"}), 401
        
        user = await user_manager.get_user_by_session(session_id)
        if not user:
            logger.warning("Invalid or expired session")
            return jsonify({"error": "Invalid or expired session"}), 401
        
        # Add the user to the kwargs so the endpoint can access it
        kwargs['user'] = user
        
        # If authenticated, proceed with the original function
        if asyncio.iscoroutinefunction(f):
            return await f(*args, **kwargs)
        else:
            return f(*args, **kwargs)
    
    return decorated_function

def require_admin(f):
    """Decorator to require admin privileges for an endpoint."""
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        session_id = request.cookies.get('discord_session')
        if not session_id:
            logger.warning("No session ID in request")
            return jsonify({"error": "Authentication required"}), 401
        
        user = await user_manager.get_user_by_session(session_id)
        if not user:
            logger.warning("Invalid or expired session")
            return jsonify({"error": "Invalid or expired session"}), 401
        
        if not user.get('is_admin'):
            logger.warning(f"User {user['id']} attempted to access admin endpoint without privileges")
            return jsonify({"error": "Admin privileges required"}), 403
        
        # Add the user to the kwargs so the endpoint can access it
        kwargs['user'] = user
        
        # If authenticated and authorized, proceed with the original function
        if asyncio.iscoroutinefunction(f):
            return await f(*args, **kwargs)
        else:
            return f(*args, **kwargs)
    
    return decorated_function

def get_authenticated_user():
    """Utility function to get the currently authenticated user."""
    async def _get_user():
        session_id = request.cookies.get('discord_session')
        if not session_id:
            return None
            
        return await user_manager.get_user_by_session(session_id)
        
    # Return coroutine that caller must await
    return _get_user()

def validate_token(token):
    """
    Validate an access token.
    This is a placeholder function for JWT validation in future implementations.
    """
    # Currently using simple API key validation
    return token == API_SECRET_KEY