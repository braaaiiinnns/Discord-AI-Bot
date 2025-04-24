"""Debug utility to help diagnose API issues"""

import os
import sys
from quart import Blueprint, jsonify, request, current_app
from utils.logger import setup_logger

# Set up logger
logger = setup_logger('discord_bot.api.debug')

# Create debug blueprint
debug_bp = Blueprint('debug', __name__, url_prefix='/api/debug')

@debug_bp.route('/headers')
async def debug_headers():
    """Return the headers received in the request"""
    logger.info("Debug headers endpoint accessed")
    
    return jsonify({
        'status': 'success',
        'request_headers': dict(request.headers),
        'method': request.method,
        'path': request.path,
        'origin': request.headers.get('Origin', 'Not specified')
    })

@debug_bp.route('/config')
async def debug_config():
    """Return the current configuration settings (non-sensitive)"""
    logger.info("Debug config endpoint accessed")
    
    # Filter out sensitive info like secrets
    safe_config = {
        'ALLOWED_ORIGINS': current_app.config.get('ALLOWED_ORIGINS', 'Not specified'),
        'SESSION_TYPE': current_app.config.get('SESSION_TYPE', 'Not specified'),
        'PERMANENT_SESSION_LIFETIME': str(current_app.config.get('PERMANENT_SESSION_LIFETIME', 'Not specified')),
        'SESSION_COOKIE_SECURE': current_app.config.get('SESSION_COOKIE_SECURE', 'Not specified'),
        'SESSION_COOKIE_HTTPONLY': current_app.config.get('SESSION_COOKIE_HTTPONLY', 'Not specified'),
        'SESSION_COOKIE_SAMESITE': current_app.config.get('SESSION_COOKIE_SAMESITE', 'Not specified'),
        'FLASK_ENV': os.environ.get('FLASK_ENV', 'development')
    }
    
    return jsonify({
        'status': 'success',
        'config': safe_config,
        'request_info': {
            'origin': request.headers.get('Origin', 'Not specified'),
            'host': request.host,
            'method': request.method,
            'path': request.path
        }
    })

@debug_bp.route('/environment')
async def debug_environment():
    """Return information about the server environment"""
    logger.info("Debug environment endpoint accessed")
    
    # Filter out sensitive environment variables
    safe_env = {}
    for key in os.environ:
        if not any(x in key.lower() for x in ['key', 'secret', 'token', 'pass', 'auth']):
            safe_env[key] = os.environ[key]
    
    return jsonify({
        'status': 'success',
        'environment': safe_env,
        'python_version': sys.version,
        'request_info': {
            'origin': request.headers.get('Origin', 'Not specified'),
            'host': request.host
        }
    })

def register_blueprint(app):
    """Register the debug blueprint with the app"""
    app.register_blueprint(debug_bp)
    logger.info("Debug blueprint registered")
