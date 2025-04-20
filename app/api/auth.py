"""
Minimal auth implementation for API security.
Provides bare-bones authentication without the dashboard components.
"""

import os
import asyncio
from functools import wraps
from flask import request, jsonify, current_app
import logging

# Import the API key from config
from config.config import API_SECRET_KEY

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