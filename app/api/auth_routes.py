"""
Authentication routes for Discord OAuth2 authentication.
This module handles login, logout, session management, and API key operations.
"""

import asyncio
import json
import os
import secrets
import time
from typing import Dict, Any, Optional, Tuple

import aiohttp
import requests
from flask import Blueprint, request, jsonify, session, redirect, url_for, current_app
from werkzeug.exceptions import BadRequest, Unauthorized, InternalServerError

from .user_model import user_manager
from utils.logger import setup_logger

# Set up logger
logger = setup_logger('discord_bot.api.auth_routes')

# Discord OAuth2 configuration
DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.environ.get('DISCORD_CLIENT_SECRET')
DISCORD_REDIRECT_URI = os.environ.get('DISCORD_REDIRECT_URI', 'http://localhost:5000/api/auth/callback')
DISCORD_API_BASE_URL = 'https://discord.com/api/v10'
DISCORD_AUTH_URL = f'{DISCORD_API_BASE_URL}/oauth2/authorize'
DISCORD_TOKEN_URL = f'{DISCORD_API_BASE_URL}/oauth2/token'
DISCORD_USER_URL = f'{DISCORD_API_BASE_URL}/users/@me'

# Create Blueprint for auth routes
auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# Helper functions
def get_session_id() -> Optional[str]:
    """Get the session ID from the request cookies."""
    return request.cookies.get('session_id')

def get_auth_header(token: str) -> Dict[str, str]:
    """Get the Authorization header for Discord API requests."""
    return {'Authorization': f'Bearer {token}'}

async def exchange_code(code: str) -> Dict[str, Any]:
    """Exchange an authorization code for an access token."""
    data = {
        'client_id': DISCORD_CLIENT_ID,
        'client_secret': DISCORD_CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': DISCORD_REDIRECT_URI
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(DISCORD_TOKEN_URL, data=data) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                logger.error(f"Failed to exchange code: {error_text}")
                raise Exception(f"Failed to exchange code: {error_text}")
            return await resp.json()

async def get_discord_user(token: str) -> Dict[str, Any]:
    """Get the Discord user information."""
    headers = get_auth_header(token)
    
    async with aiohttp.ClientSession() as session:
        async with session.get(DISCORD_USER_URL, headers=headers) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                logger.error(f"Failed to get user info: {error_text}")
                raise Exception(f"Failed to get user info: {error_text}")
            return await resp.json()

def get_oauth2_url() -> str:
    """Get the Discord OAuth2 authorization URL."""
    params = {
        'client_id': DISCORD_CLIENT_ID,
        'redirect_uri': DISCORD_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'identify email'
    }
    
    from urllib.parse import urlencode
    auth_url = f"{DISCORD_AUTH_URL}?{urlencode(params)}"
    return auth_url

# Routes
@auth_bp.route('/login')
def login():
    """Redirect the user to the Discord OAuth2 authorization page."""
    # Generate and store a state token to prevent CSRF
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    
    # Generate the Discord OAuth2 URL
    auth_url = get_oauth2_url()
    
    # Redirect to Discord OAuth2
    return redirect(auth_url)

@auth_bp.route('/callback')
async def callback():
    """Handle the Discord OAuth2 callback."""
    # Get the authorization code
    code = request.args.get('code')
    
    if not code:
        logger.error("No authorization code provided")
        return jsonify({'error': 'No authorization code provided'}), 400
    
    try:
        # Exchange the code for an access token
        token_data = await exchange_code(code)
        
        # Get the user information
        user_data = await get_discord_user(token_data['access_token'])
        
        # Create or update the user record
        user = await user_manager.create_or_update_user(user_data, token_data)
        
        # Create a session for the user
        session_id = await user_manager.create_session(user['id'])
        
        if not session_id:
            logger.error("Failed to create session")
            return jsonify({'error': 'Failed to create session'}), 500
        
        # Create response with session cookie
        response = redirect('/dashboard')
        
        # Set the session cookie
        response.set_cookie(
            'session_id', 
            session_id, 
            httponly=True, 
            secure=request.is_secure, 
            samesite='Lax',
            max_age=30 * 24 * 60 * 60  # 30 days
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error during OAuth2 callback: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/logout')
async def logout():
    """Log out the user by deleting their session."""
    session_id = get_session_id()
    
    if session_id:
        await user_manager.delete_session(session_id)
    
    response = redirect('/')
    response.delete_cookie('session_id')
    
    return response

@auth_bp.route('/user')
async def get_user():
    """Get the current user's information."""
    session_id = get_session_id()
    
    if not session_id:
        return jsonify({'authenticated': False}), 401
    
    user = await user_manager.get_user_by_session(session_id)
    
    if not user:
        response = jsonify({'authenticated': False})
        response.delete_cookie('session_id')
        return response, 401
    
    # Return user data, excluding sensitive information
    return jsonify({
        'authenticated': True,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'discriminator': user['discriminator'],
            'avatar': user['avatar'],
            'email': user['email'],
            'api_key': user['api_key'],
            'is_admin': user['is_admin']
        }
    })

@auth_bp.route('/key', methods=['GET'])
async def get_api_key():
    """Get the user's API key."""
    session_id = get_session_id()
    
    if not session_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = await user_manager.get_user_by_session(session_id)
    
    if not user:
        return jsonify({'error': 'Invalid session'}), 401
    
    return jsonify({'api_key': user['api_key']})

@auth_bp.route('/key', methods=['POST'])
async def refresh_api_key():
    """Generate a new API key for the user."""
    session_id = get_session_id()
    
    if not session_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = await user_manager.get_user_by_session(session_id)
    
    if not user:
        return jsonify({'error': 'Invalid session'}), 401
    
    # Generate a new API key
    new_api_key = secrets.token_urlsafe(32)
    
    # Update the user's API key
    success = await user_manager.update_user_api_key(user['id'], new_api_key)
    
    if not success:
        return jsonify({'error': 'Failed to update API key'}), 500
    
    return jsonify({'api_key': new_api_key})

@auth_bp.route('/validate', methods=['POST'])
async def validate_api_key():
    """Validate an API key."""
    api_key = request.json.get('api_key')
    
    if not api_key:
        return jsonify({'valid': False, 'error': 'No API key provided'}), 400
    
    user = await user_manager.get_user_by_api_key(api_key)
    
    if not user:
        return jsonify({'valid': False}), 401
    
    return jsonify({
        'valid': True,
        'user': {
            'id': user['id'],
            'username': user['username']
        }
    })

@auth_bp.route('/admin/users')
async def admin_get_users():
    """Admin endpoint to get all users."""
    session_id = get_session_id()
    
    if not session_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = await user_manager.get_user_by_session(session_id)
    
    if not user or not user['is_admin']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    users = await user_manager.get_all_users()
    
    # Filter out sensitive information
    filtered_users = []
    for u in users:
        filtered_users.append({
            'id': u['id'],
            'username': u['username'],
            'discriminator': u['discriminator'],
            'email': u['email'],
            'avatar': u['avatar'],
            'is_admin': u['is_admin'],
            'created_at': u['created_at']
        })
    
    return jsonify({'users': filtered_users})

@auth_bp.route('/admin/users/<user_id>/admin', methods=['PUT'])
async def admin_set_admin(user_id: str):
    """Admin endpoint to set a user as admin."""
    session_id = get_session_id()
    
    if not session_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    current_user = await user_manager.get_user_by_session(session_id)
    
    if not current_user or not current_user['is_admin']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    admin_status = request.json.get('is_admin', True)
    
    success = await user_manager.set_user_admin(user_id, admin_status)
    
    if not success:
        return jsonify({'error': 'Failed to update user'}), 500
    
    return jsonify({'success': True})

@auth_bp.route('/admin/cleanup-sessions')
async def admin_cleanup_sessions():
    """Admin endpoint to clean up expired sessions."""
    session_id = get_session_id()
    
    if not session_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = await user_manager.get_user_by_session(session_id)
    
    if not user or not user['is_admin']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    count = await user_manager.clean_expired_sessions()
    
    return jsonify({'deletedCount': count})

@auth_bp.route('/access/request', methods=['POST'])
async def request_access():
    """Request access to the dashboard."""
    session_id = get_session_id()
    
    if not session_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = await user_manager.get_user_by_session(session_id)
    
    if not user:
        return jsonify({'error': 'Invalid session'}), 401
    
    # Get optional message
    message = request.json.get('message', '')
    
    # Create access request
    request_id = await user_manager.request_dashboard_access(user['id'], message)
    
    if not request_id:
        return jsonify({'error': 'Failed to create access request'}), 500
        
    # Send notification to admin via Discord
    asyncio.create_task(send_access_request_notification(user, message))
    
    return jsonify({
        'success': True, 
        'request_id': request_id,
        'status': 'pending'
    })

@auth_bp.route('/access/status')
async def check_access_status():
    """Check the status of the user's dashboard access."""
    session_id = get_session_id()
    
    if not session_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = await user_manager.get_user_by_session(session_id)
    
    if not user:
        return jsonify({'error': 'Invalid session'}), 401
    
    # Get access status from user record
    access_status = user.get('access_status', 'pending')
    
    return jsonify({
        'status': access_status,
        'is_admin': user.get('is_admin', False)
    })

@auth_bp.route('/admin/access/requests')
async def admin_get_access_requests():
    """Admin endpoint to get all pending access requests."""
    session_id = get_session_id()
    
    if not session_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = await user_manager.get_user_by_session(session_id)
    
    if not user or not user['is_admin']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    requests = await user_manager.get_pending_access_requests()
    
    return jsonify({'requests': requests})

@auth_bp.route('/admin/access/approve/<request_id>', methods=['POST'])
async def admin_approve_access(request_id):
    """Admin endpoint to approve an access request."""
    session_id = get_session_id()
    
    if not session_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    admin_user = await user_manager.get_user_by_session(session_id)
    
    if not admin_user or not admin_user['is_admin']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    success, user = await user_manager.approve_access_request(request_id)
    
    if not success:
        return jsonify({'error': 'Failed to approve request'}), 500
        
    # Send notification to the user via Discord
    if user:
        asyncio.create_task(send_access_approved_notification(user))
    
    return jsonify({'success': True})

@auth_bp.route('/admin/access/deny/<request_id>', methods=['POST'])
async def admin_deny_access(request_id):
    """Admin endpoint to deny an access request."""
    session_id = get_session_id()
    
    if not session_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    admin_user = await user_manager.get_user_by_session(session_id)
    
    if not admin_user or not admin_user['is_admin']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    success, user = await user_manager.deny_access_request(request_id)
    
    if not success:
        return jsonify({'error': 'Failed to deny request'}), 500
        
    # Send notification to the user via Discord
    if user:
        asyncio.create_task(send_access_denied_notification(user))
    
    return jsonify({'success': True})

@auth_bp.route('/admin/users/<user_id>/access-status', methods=['PUT'])
async def admin_update_access_status(user_id: str):
    """Admin endpoint to update a user's access status."""
    session_id = get_session_id()
    
    if not session_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    admin_user = await user_manager.get_user_by_session(session_id)
    
    if not admin_user or not admin_user['is_admin']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    status = request.json.get('status')
    if not status or status not in ['pending', 'requested', 'approved', 'denied']:
        return jsonify({'error': 'Invalid status'}), 400
    
    success = await user_manager.update_user_access_status(user_id, status)
    
    if not success:
        return jsonify({'error': 'Failed to update user status'}), 500
    
    return jsonify({'success': True})

@auth_bp.route('/admin/users/<user_id>/api-key/reset', methods=['POST'])
async def admin_reset_api_key(user_id: str):
    """Admin endpoint to reset a user's API key."""
    session_id = get_session_id()
    
    if not session_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    admin_user = await user_manager.get_user_by_session(session_id)
    
    if not admin_user or not admin_user['is_admin']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Generate a new API key
    new_api_key = secrets.token_urlsafe(32)
    
    # Update the user's API key
    success = await user_manager.update_user_api_key(user_id, new_api_key)
    
    if not success:
        return jsonify({'error': 'Failed to reset API key'}), 500
    
    return jsonify({'success': True})

# Functions to send Discord notifications
async def send_access_request_notification(user, message):
    """Send a Discord notification to admins about a new access request."""
    try:
        from app.discord.state import bot
        
        if not bot or not hasattr(bot, 'admin_users'):
            logger.warning("Discord bot not available or admin_users not defined")
            return
            
        for admin_id in bot.admin_users:
            try:
                admin_user = await bot.fetch_user(int(admin_id))
                
                if admin_user:
                    embed = {
                        'title': 'New Dashboard Access Request',
                        'description': f"User **{user['username']}** has requested access to the dashboard.",
                        'color': 0x5865F2,  # Discord Blue
                        'fields': [
                            {
                                'name': 'User ID',
                                'value': user['id'],
                                'inline': True
                            },
                            {
                                'name': 'Email',
                                'value': user.get('email', 'No email provided'),
                                'inline': True
                            }
                        ],
                        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S.%fZ', time.gmtime())
                    }
                    
                    if message:
                        embed['fields'].append({
                            'name': 'Message',
                            'value': message,
                            'inline': False
                        })
                    
                    await admin_user.send(embed=embed)
                    logger.info(f"Sent access request notification to admin {admin_id}")
            except Exception as e:
                logger.error(f"Failed to send notification to admin {admin_id}: {e}")
    except Exception as e:
        logger.error(f"Error sending access request notification: {e}")

async def send_access_approved_notification(user):
    """Send a Discord notification to a user that their access was approved."""
    try:
        from app.discord.state import bot
        
        if not bot:
            logger.warning("Discord bot not available")
            return
            
        try:
            discord_user = await bot.fetch_user(int(user['id']))
            
            if discord_user:
                embed = {
                    'title': 'Dashboard Access Approved',
                    'description': "Your request for dashboard access has been approved!",
                    'color': 0x43B581,  # Discord Green
                    'fields': [
                        {
                            'name': 'Next Steps',
                            'value': "You can now log in to the dashboard and access all features.",
                            'inline': False
                        }
                    ],
                    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S.%fZ', time.gmtime())
                }
                
                await discord_user.send(embed=embed)
                logger.info(f"Sent access approval notification to user {user['id']}")
        except Exception as e:
            logger.error(f"Failed to send approval notification to user {user['id']}: {e}")
    except Exception as e:
        logger.error(f"Error sending access approval notification: {e}")

async def send_access_denied_notification(user):
    """Send a Discord notification to a user that their access was denied."""
    try:
        from app.discord.state import bot
        
        if not bot:
            logger.warning("Discord bot not available")
            return
            
        try:
            discord_user = await bot.fetch_user(int(user['id']))
            
            if discord_user:
                embed = {
                    'title': 'Dashboard Access Denied',
                    'description': "Your request for dashboard access has been denied.",
                    'color': 0xF04747,  # Discord Red
                    'fields': [
                        {
                            'name': 'Questions?',
                            'value': "If you believe this is an error, please contact the server administrator.",
                            'inline': False
                        }
                    ],
                    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S.%fZ', time.gmtime())
                }
                
                await discord_user.send(embed=embed)
                logger.info(f"Sent access denial notification to user {user['id']}")
        except Exception as e:
            logger.error(f"Failed to send denial notification to user {user['id']}: {e}")
    except Exception as e:
        logger.error(f"Error sending access denial notification: {e}")

def register_blueprint(app):
    """Register the auth blueprint with the Flask app."""
    app.register_blueprint(auth_bp)