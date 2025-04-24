"""
Auth debugging module to help diagnose login issues
"""
import os
import logging
import traceback
from quart import Blueprint, jsonify, session, request, redirect, current_app
from urllib.parse import urlencode

logger = logging.getLogger('discord_bot.api.auth_debug')

auth_debug_bp = Blueprint('auth_debug', __name__)

@auth_debug_bp.route('/api/debug/auth/status')
async def auth_status():
    """Check the current auth status"""
    try:
        session_data = {k: v for k, v in session.items() if k != 'csrf_token'}
        user_data = session.get('user', None)
        user_summary = {
            "logged_in": bool(user_data),
            "user_id": user_data.get('id') if user_data else None,
            "username": user_data.get('username') if user_data else None
        }
        
        return jsonify({
            "auth_status": "authenticated" if user_data else "unauthenticated",
            "user": user_summary,
            "session_active": bool(session_data)
        })
    except Exception as e:
        logger.error(f"Error in auth status: {str(e)}", exc_info=True)
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc(),
            "session_working": False
        }), 500

@auth_debug_bp.route('/api/debug/auth/test-login')
async def test_login():
    """Test the login flow by manually triggering the Discord OAuth URL"""
    try:
        from .auth_routes import get_oauth_url
        oauth_url = get_oauth_url()
        
        # Log details about the generated URL
        logger.info(f"Generated OAuth URL: {oauth_url}")
        
        # Test if the redirect URL is properly set
        redirect_uri = os.environ.get('DISCORD_REDIRECT_URI', 'http://localhost:8050/callback')
        
        return jsonify({
            "status": "ok",
            "login_url": oauth_url,
            "redirect_uri": redirect_uri,
            "expected_flow": [
                "1. Click the login URL",
                "2. Authorize with Discord",
                "3. Discord redirects to your redirect_uri with code and state",
                "4. Your server processes the callback"
            ],
            "environment_check": {
                "client_id_set": bool(os.environ.get('DISCORD_CLIENT_ID')),
                "client_secret_set": bool(os.environ.get('DISCORD_CLIENT_SECRET')),
                "redirect_uri_set": bool(os.environ.get('DISCORD_REDIRECT_URI'))
            }
        })
    except Exception as e:
        logger.error(f"Error generating test login: {str(e)}", exc_info=True)
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500

@auth_debug_bp.route('/api/debug/auth/simulate-login')
async def simulate_login():
    """Simulate a successful login for testing"""
    try:
        # Only allow in development mode
        if os.environ.get('FLASK_ENV') != 'development':
            return jsonify({"error": "This endpoint is only available in development mode"}), 403
            
        # Create a test user in session
        session['user'] = {
            'id': '123456789',
            'username': 'test_user',
            'avatar': None,
            'discriminator': '0000',
            'public_flags': 0,
            'flags': 0,
            'banner': None,
            'accent_color': None,
            'global_name': 'Test User',
            'avatar_decoration_data': None,
            'banner_color': None
        }
        session['logged_in'] = True
        session['oauth_state'] = 'test_state'
        
        return jsonify({
            "status": "success",
            "message": "Simulated login successful",
            "user": {
                "id": session['user']['id'],
                "username": session['user']['username']
            }
        })
    except Exception as e:
        logger.error(f"Error simulating login: {str(e)}", exc_info=True)
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500

def register_blueprint(app):
    """Register the auth debug blueprint with the app"""
    app.register_blueprint(auth_debug_bp)
    logger.info("Registered auth debug blueprint")
