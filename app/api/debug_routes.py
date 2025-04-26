"""Debug routes to help troubleshoot API issues"""

import os
import sys
import platform
import traceback
from quart import Blueprint, jsonify, request, current_app, session
from utils.logger import setup_logger
from .user_model import user_manager
from utils.api_key_manager import api_key_manager

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

@debug_bp.route('/auth-diagnostic')
async def auth_diagnostic():
    """Detailed diagnostics for authentication troubleshooting"""
    logger.info("Auth diagnostic endpoint accessed")
    
    # Get authentication-related headers
    auth_header = request.headers.get('Authorization')
    api_key_header = request.headers.get('X-API-Key')
    
    # Parse API key from headers
    api_key = None
    auth_method = None
    
    if auth_header and auth_header.startswith('Bearer '):
        api_key = auth_header[7:].strip()
        auth_method = 'Bearer token'
    elif api_key_header:
        api_key = api_key_header.strip()
        auth_method = 'X-API-Key header'
    
    # Check if there's a session cookie and get session ID
    session_id = request.cookies.get('session_id')
    has_session = bool(session_id)
    
    # Attempt to validate the API key if present
    api_key_valid = False
    key_info = None
    api_key_preview = None
    
    if api_key:
        api_key_preview = api_key[:5] + '...' if len(api_key) > 5 else '[invalid]'
        try:
            # Check system API keys
            api_key_valid = api_key_manager.validate_key(api_key)
            if api_key_valid:
                key_info = api_key_manager.extract_data_from_key(api_key)
                key_info['type'] = 'system'
        except Exception as e:
            logger.error(f"Error validating system API key: {e}")
    
    # Check user API key in database
    user_from_api_key = None
    user_from_session = None
    
    try:
        if api_key and not api_key_valid:
            user_from_api_key = await user_manager.get_user_by_api_key(api_key)
            if user_from_api_key:
                api_key_valid = True
                key_info = {
                    'type': 'user',
                    'user_id': user_from_api_key.get('id'),
                    'username': user_from_api_key.get('username')
                }
    except Exception as e:
        logger.error(f"Error checking user API key: {e}")
    
    # Check session authentication
    session_valid = False
    try:
        if session_id:
            user_from_session = await user_manager.get_user_by_session(session_id)
            if user_from_session:
                session_valid = True
    except Exception as e:
        logger.error(f"Error checking session: {e}")
    
    # Capture all request headers (excluding sensitive data)
    filtered_headers = {}
    for key, value in request.headers.items():
        # Omit sensitive headers
        if key.lower() in ('cookie', 'authorization'):
            filtered_headers[key] = '[FILTERED]'
        else:
            filtered_headers[key] = value
    
    # Quart Session Data
    quart_session_data = None
    try:
        session_keys = list(session.keys()) if session else []
        if session_keys:
            quart_session_data = {
                'keys': session_keys,
                'has_user': 'user' in session,
                'logged_in': session.get('logged_in', False),
                'login_time': session.get('login_time')
            }
    except Exception as e:
        logger.error(f"Error accessing session data: {e}")
        quart_session_data = {'error': str(e)}
    
    # User info summary (if authenticated)
    authenticated_user = None
    if user_from_api_key or user_from_session:
        user = user_from_api_key or user_from_session
        authenticated_user = {
            'id': user.get('id'),
            'username': user.get('username'),
            'is_admin': user.get('is_admin', False),
            'access_status': user.get('access_status', 'unknown'),
            'auth_method': 'API Key' if user_from_api_key else 'Session',
            'has_api_key': bool(user.get('api_key'))
        }
    
    # Assemble diagnostic data
    diagnostic_data = {
        'timestamp': str(datetime.utcnow()),
        'request_path': request.path,
        'request_method': request.method,
        'auth_method_used': auth_method,
        'api_key_present': bool(api_key),
        'api_key_preview': api_key_preview if api_key else None,
        'api_key_valid': api_key_valid,
        'api_key_info': key_info,
        'session_cookie_present': has_session,
        'session_valid': session_valid,
        'quart_session': quart_session_data,
        'authenticated_user': authenticated_user,
        'headers': filtered_headers,
        'user_agent': request.headers.get('User-Agent'),
        'origin': request.headers.get('Origin'),
        'referer': request.headers.get('Referer'),
        'host': request.host,
        'remote_addr': request.remote_addr
    }
    
    # Add to logs for future reference
    logger.info(f"Auth diagnostic complete for {request.remote_addr}: " +
                f"API Key Valid: {api_key_valid}, Session Valid: {session_valid}")
    
    return jsonify({
        'status': 'success',
        'message': 'Authentication diagnostic results',
        'diagnostics': diagnostic_data,
        'recommendation': get_auth_recommendation(diagnostic_data)
    })

def get_auth_recommendation(diagnostic):
    """Generate recommendations based on diagnostic data"""
    recommendations = []
    
    if not diagnostic['api_key_present'] and not diagnostic['session_cookie_present']:
        recommendations.append("No authentication credentials provided. Add either an API key via 'Authorization: Bearer YOUR_API_KEY' header or 'X-API-Key: YOUR_API_KEY' header.")
        recommendations.append("Make sure you're logged in to get a valid session cookie if using session-based authentication.")
    
    elif diagnostic['api_key_present'] and not diagnostic['api_key_valid']:
        recommendations.append("Invalid API key provided. Check that you're using the correct API key.")
        recommendations.append("API keys can be obtained from your user profile or generated in the dashboard settings.")
        if diagnostic['session_cookie_present'] and not diagnostic['session_valid']:
            recommendations.append("Your session is also invalid. Consider logging in again.")
    
    elif diagnostic['api_key_valid'] and not diagnostic['authenticated_user']:
        recommendations.append("Your API key is valid but doesn't correspond to a user. This may be a system API key.")
        recommendations.append("For user-specific operations, you need to use a user API key or have a valid session.")
    
    elif diagnostic['session_cookie_present'] and not diagnostic['session_valid']:
        recommendations.append("Your session is invalid or expired. Try logging in again.")
        if diagnostic['api_key_valid']:
            recommendations.append("However, your API key is valid and can be used for authentication.")
    
    elif diagnostic['authenticated_user'] and diagnostic['authenticated_user']['access_status'] != 'approved':
        status = diagnostic['authenticated_user']['access_status']
        recommendations.append(f"Your access status is '{status}'. You need 'approved' status to access protected resources.")
        recommendations.append("Contact an administrator to approve your account.")
    
    else:
        recommendations.append("Authentication appears to be working correctly.")
        if diagnostic['authenticated_user']:
            auth_method = diagnostic['authenticated_user']['auth_method']
            recommendations.append(f"You are authenticated via {auth_method} as {diagnostic['authenticated_user']['username']}.")
    
    return recommendations

def register_blueprint(app):
    """Register the debug blueprint with the app"""
    app.register_blueprint(debug_bp)
    logger.info("Debug blueprint registered")
