"""Debug routes to help troubleshoot API issues"""

import os
import sys
import platform
from quart import Blueprint, jsonify, request, current_app
from utils.logger import setup_logger

# Set up logger
logger = setup_logger('discord_bot.api.debug')

# Create debug blueprint
debug_bp = Blueprint('debug', __name__, url_prefix='/api/debug')

@debug_bp.route('/info')
async def debug_info():
    """Return debugging information about the server environment"""
    logger.info("Debug info endpoint accessed")
    
    # Get information about the environment
    env_info = {
        'python_version': sys.version,
        'platform': platform.platform(),
        'environment': os.environ.get('FLASK_ENV', 'development'),
        'quart_debug': current_app.debug,
        'allowed_origins': current_app.config.get('ALLOWED_ORIGINS', '*'),
        'session_type': current_app.config.get('SESSION_TYPE', 'unknown'),
        'app_name': current_app.name
    }
    
    # Get request information
    request_info = {
        'path': request.path,
        'method': request.method,
        'headers': dict(request.headers),
        'host': request.host,
        'cookies': request.cookies
    }
    
    return jsonify({
        'status': 'success',
        'message': 'Debug information',
        'environment': env_info,
        'request': request_info
    })

@debug_bp.route('/cors-test')
async def cors_test():
    """Simple endpoint to test CORS configuration"""
    logger.info("CORS test endpoint accessed")
    return jsonify({
        'status': 'success',
        'message': 'CORS is properly configured if you can see this message',
        'request_headers': dict(request.headers)
    })

@debug_bp.route('/session-test')
async def session_test():
    """Test session storage and retrieval"""
    from quart import session
    
    # Get current visit count or set to 0
    visit_count = session.get('visit_count', 0)
    # Increment the counter
    visit_count += 1
    # Store back in session
    session['visit_count'] = visit_count
    
    return jsonify({
        'status': 'success',
        'message': 'Session test',
        'visit_count': visit_count,
        'session_data': {k: v for k, v in session.items() if k != 'csrf_token'}
    })

def register_blueprint(app):
    """Register the debug blueprint with the app"""
    app.register_blueprint(debug_bp)
    logger.info("Debug blueprint registered")
