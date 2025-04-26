"""
API middleware functions for authentication and request processing.
"""

import logging
from functools import wraps
from quart import request, jsonify
import os
from utils.api_key_manager import api_key_manager
from .user_model import user_manager
import asyncio
import json
import traceback

# Set up logger
logger = logging.getLogger('discord_bot.api.middleware')

async def authenticate_request(optional=False):
    """
    Authenticate a request using API key.
    
    Args:
        optional: If True, continue without API key validation
        
    Returns:
        Tuple of (user, api_key) if authenticated, or (None, None) if not
    """
    # Get API key from headers
    api_key = None
    auth_header = request.headers.get('Authorization')
    if (auth_header and auth_header.startswith('Bearer ')):
        api_key = auth_header[7:].strip()  # Remove 'Bearer ' prefix and whitespace
    
    # Also check X-API-Key header as alternative
    if not api_key:
        api_key = request.headers.get('X-API-Key')
        if api_key:
            api_key = api_key.strip()
    
    # Get request info for logging
    req_path = request.path
    req_method = request.method
    req_origin = request.headers.get('Origin', 'Unknown')
    req_referer = request.headers.get('Referer', 'Unknown')
    req_user_agent = request.headers.get('User-Agent', 'Unknown')
    
    # Enhanced logging: Log all authentication request details
    request_id = request.headers.get('X-Request-ID', f"req_{id(request)}")
    log_prefix = f"[{request_id}][{req_method} {req_path}]"
    
    # Check for empty or invalid keys
    if not api_key or api_key == "undefined" or api_key == "null" or len(api_key) < 8:
        if optional:
            logger.debug(f"{log_prefix} No valid API key provided, but authentication is optional")
            logger.debug(f"{log_prefix} Client details: Origin={req_origin}, Referer={req_referer}, UA={req_user_agent[:50]}")
            return None, None
        logger.warning(f"{log_prefix} Invalid or missing API key")
        logger.debug(f"{log_prefix} Client details: Origin={req_origin}, Referer={req_referer}, UA={req_user_agent[:50]}")
        # Enhanced logging: Log all headers for problematic requests
        header_log = {k: v for k, v in request.headers.items() if k.lower() not in ('cookie', 'authorization')}
        logger.debug(f"{log_prefix} Request headers: {json.dumps(header_log)}")
        return None, None
    
    # Validate the key using our API key manager
    is_valid = api_key_manager.validate_key(api_key)
    
    if is_valid:
        logger.debug(f"{log_prefix} Valid system API key: {api_key[:5]}...")
        return None, api_key
    
    # If it's not a system key, check if it's a user-specific API key
    try:
        user = await user_manager.get_user_by_api_key(api_key)
        if user:
            logger.debug(f"{log_prefix} Valid user API key for user: {user['username']}")
            return user, api_key
        else:
            # Enhanced logging: Log detailed diagnostics for invalid keys
            logger.warning(f"{log_prefix} User lookup failed for API key {api_key[:5]}...")
            logger.debug(f"{log_prefix} Client details: Origin={req_origin}, Referer={req_referer}")
    except Exception as e:
        logger.error(f"{log_prefix} Error checking user API key: {e}")
        logger.error(f"{log_prefix} Exception details: {traceback.format_exc()}")
    
    # Invalid key
    logger.warning(f"{log_prefix} Invalid API key: {api_key[:5]}...")
    return None, None

def require_auth(optional=False, require_user=False, admin_only=False, endpoint_name=None):
    """
    Decorator to require API key authentication for a route.
    
    Args:
        optional: If True, proceed even if no API key is provided
        require_user: If True, require a user-specific API key
        admin_only: If True, require the user to be an admin
        endpoint_name: Optional name for this endpoint for better logging
        
    Returns:
        Decorated function
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = asyncio.get_event_loop().time()
            endpoint = endpoint_name or func.__name__
            req_path = request.path
            req_method = request.method
            request_id = request.headers.get('X-Request-ID', f"req_{id(request)}")
            log_prefix = f"[{request_id}][{req_method} {req_path}][{endpoint}]"
            
            # Enhanced intro logging
            logger.info(f"{log_prefix} Auth request started")
            
            try:
                # Log request format details
                content_type = request.headers.get('Content-Type', 'None')
                accept = request.headers.get('Accept', 'None')
                logger.debug(f"{log_prefix} Request format: Content-Type={content_type}, Accept={accept}")
                
                user, api_key = await authenticate_request(optional)
                
                # Check if this appears to be a dashboard refresh request
                is_refresh_request = request.headers.get('Referer', '').endswith('/dashboard') and \
                                    request.headers.get('X-Requested-With', '') == 'XMLHttpRequest'
                
                if not optional and not api_key:
                    # Use debug level for likely dashboard refresh requests to reduce log noise
                    if is_refresh_request:
                        logger.debug(f"{log_prefix} Refresh authentication failed: No valid API key")
                    else:
                        logger.warning(f"{log_prefix} Authentication failed: No valid API key")
                    
                    return jsonify({
                        "error": "Authentication required", 
                        "message": "Valid API key required",
                        "endpoint": req_path,
                        "request_id": request_id
                    }), 401
                
                if require_user and not user:
                    logger.warning(f"{log_prefix} Authentication failed: No valid user API key")
                    return jsonify({
                        "error": "User authentication required", 
                        "message": "Valid user API key required",
                        "endpoint": req_path,
                        "request_id": request_id
                    }), 401
                
                if admin_only and (not user or not user.get('is_admin')):
                    # Add a small delay to prevent timing attacks
                    await asyncio.sleep(0.5)
                    logger.warning(f"{log_prefix} Authorization failed: Admin access required")
                    return jsonify({
                        "error": "Access denied", 
                        "message": "Admin access required",
                        "endpoint": req_path,
                        "request_id": request_id
                    }), 403
                
                # Store the user in request.user for use in the route handler
                request.user = user
                request.api_key = api_key
                
                # Log success
                if user:
                    logger.info(f"{log_prefix} Authentication successful for user: {user['username']}")
                elif api_key:
                    logger.info(f"{log_prefix} Authentication successful with system API key")
                else:
                    logger.info(f"{log_prefix} No authentication required (optional=True)")
                
                # Call the route handler
                response = await func(*args, **kwargs)
                
                # Log completion
                elapsed_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                status_code = response[1] if isinstance(response, tuple) and len(response) > 1 else 200
                logger.info(f"{log_prefix} Request completed: status={status_code}, time={elapsed_ms:.2f}ms")
                
                return response
                
            except Exception as e:
                elapsed_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                logger.error(f"{log_prefix} Error in auth middleware after {elapsed_ms:.2f}ms: {e}")
                logger.error(f"{log_prefix} Exception details: {traceback.format_exc()}")
                return jsonify({
                    "error": "Server error",
                    "message": "An error occurred during authentication",
                    "request_id": request_id
                }), 500
                
        return wrapper
    return decorator