import os
import secrets
from quart import Quart, redirect, send_from_directory, request, url_for, abort, jsonify, make_response
from quart_cors import cors
import logging
from datetime import datetime, timedelta
from config.storage_config import FLASK_SESSION_DIR
from typing import Callable, Dict, List, Optional
from .session_handler import setup_session_handler

# Import API key manager
from utils.api_key_manager import api_key_manager

# Set up logger
logger = logging.getLogger('discord_bot.api')

# ASGI middleware for handling proxy headers
class TrustedHostMiddleware:
    """ASGI middleware for handling X-Forwarded-For and similar headers from trusted proxies.
    This is an ASGI-compatible replacement for Werkzeug's ProxyFix."""
    
    def __init__(self, app: Callable, trusted_hosts: Optional[List[str]] = None,
                 num_proxies: int = 1) -> None:
        self.app = app
        self.trusted_hosts = trusted_hosts or ['127.0.0.1', 'localhost']
        self.num_proxies = num_proxies
        logger.info(f"TrustedHostMiddleware initialized with {num_proxies} proxies and trusted hosts: {self.trusted_hosts}")
    
    async def __call__(self, scope: Dict, receive: Callable, send: Callable) -> None:
        """Process ASGI request with proper proxy header handling"""
        if scope["type"] != "http":
            # Pass through non-HTTP requests unchanged
            await self.app(scope, receive, send)
            return
            
        # Check if the client IP is in trusted hosts
        client_addr = scope.get('client')
        if client_addr:
            client_host = client_addr[0]
            if any(client_host == host or (host.startswith('*') and client_host.endswith(host[1:])) 
                   for host in self.trusted_hosts):
                # This is a trusted host, process headers
                headers = scope.get('headers', [])
                headers_dict = {k.decode('latin1').lower(): v.decode('latin1') 
                               for k, v in headers}
                
                # Handle X-Forwarded-For
                if 'x-forwarded-for' in headers_dict:
                    forwarded_for = headers_dict['x-forwarded-for'].split(',')
                    if len(forwarded_for) >= self.num_proxies:
                        # Get the original client's IP
                        real_ip = forwarded_for[-(self.num_proxies+1)].strip()
                        # Update the client address with the real IP
                        scope['client'] = (real_ip, scope['client'][1])
                
                # Handle X-Forwarded-Proto
                if 'x-forwarded-proto' in headers_dict:
                    scheme = headers_dict['x-forwarded-proto'].split(',')[0].strip()
                    scope['scheme'] = scheme
                    
                # Handle X-Forwarded-Host
                if 'x-forwarded-host' in headers_dict:
                    host = headers_dict['x-forwarded-host'].split(',')[0].strip()
                    headers = [(k, v) for k, v in headers if k.decode('latin1').lower() != 'host']
                    headers.append((b'host', host.encode('latin1')))
                    scope['headers'] = headers
        
        # Continue with the request
        await self.app(scope, receive, send)

# Initialize Quart app
app = Quart(__name__)

# Security improvement 1: Add ASGI-compatible trusted host middleware for proper header handling behind proxies
app.asgi_app = TrustedHostMiddleware(
    app.asgi_app, 
    trusted_hosts=['127.0.0.1', 'localhost', '*example.com'],
    num_proxies=1
)

# Security improvement 2: More robust secret key handling
secret_key = os.environ.get('FLASK_SECRET_KEY')
if not secret_key:
    # In production, abort startup if no secret key is provided
    if os.environ.get('FLASK_ENV') == 'production':
        logger.critical("No FLASK_SECRET_KEY environment variable set in production mode. Aborting for security.")
        raise RuntimeError("FLASK_SECRET_KEY must be set in production environment")
    # In development, generate a random secret key for this session only
    secret_key = secrets.token_hex(32)
    logger.warning("Generated temporary SECRET_KEY for development. DO NOT use in production!")

# Security improvement 3: Enhanced session configuration with compatible backend for Quart
app.config.update(
    SECRET_KEY=secret_key,
    SESSION_TYPE='redis',  # Using Redis for session storage
    SESSION_REDIS=os.environ.get('REDIS_URL', 'redis://localhost:6379/0'),  # Default Redis URL
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),  # 12 hour session lifetime
    SESSION_COOKIE_SECURE=os.environ.get('FLASK_ENV') == 'production',  # Secure in production
    SESSION_COOKIE_HTTPONLY=True,  # Not accessible via JavaScript
    SESSION_COOKIE_SAMESITE='Lax',  # Prevent CSRF
    SESSION_USE_SIGNER=True,  # Sign session cookie for additional security
    MAX_CONTENT_LENGTH=50 * 1024 * 1024,  # Limit request size to 50MB
    JSON_SORT_KEYS=False,  # Don't sort JSON keys for better performance
    JSONIFY_PRETTYPRINT_REGULAR=False,  # Don't prettify JSON in production
    SESSION_KEY_PREFIX='discord_bot_session:',  # Prefix for Redis keys
)

# Setup session handling using the new module
setup_session_handler(app, FLASK_SESSION_DIR)

# Security improvement 5: Configure CORS properly with specific origins
allowed_origins = os.environ.get('ALLOWED_ORIGINS', 'http://localhost:8050,http://127.0.0.1:8050').split(',')

# For development, when needed, uncomment to allow all origins
# allowed_origins = ["*"]

cors_max_age = 3600  # 1 hour cache for preflight requests

# Enhanced CORS configuration
app = cors(app, 
    allow_origin=allowed_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
    allow_credentials=True,
    max_age=cors_max_age,
    expose_headers=['Content-Disposition']
)

# Add a middleware to ensure CORS headers are always set
@app.after_request
async def add_cors_headers(response):
    """Ensure CORS headers are included in all responses"""
    # Add CORS headers for the specific origin that made the request
    origin = request.headers.get('Origin')
    if origin and (origin in allowed_origins or "*" in allowed_origins):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
    return response

# Explicitly handle OPTIONS requests for CORS preflight
@app.route('/<path:path>', methods=['OPTIONS'])
@app.route('/', methods=['OPTIONS'])
async def handle_options(path=""):
    """Handle OPTIONS requests for CORS preflight"""
    response = await make_response("")
    origin = request.headers.get('Origin')
    if origin and (origin in allowed_origins or "*" in allowed_origins):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        response.headers['Access-Control-Max-Age'] = str(cors_max_age)
    return response

# Ensure OPTIONS requests are handled properly for CORS preflight
@app.route('/', methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
async def options_handler(path=""):
    """Handle OPTIONS requests for CORS preflight"""
    # Just return empty response with proper CORS headers
    # The @cors decorator will handle adding the headers
    return ''

# Security improvement 6: Add security headers to all responses
@app.after_request
async def add_security_headers(response):
    """Add security headers to all responses"""
    # Content Security Policy
    csp = {
        'default-src': ["'self'"],
        'img-src': ["'self'", 'data:', 'https://cdn.discordapp.com'],
        'script-src': ["'self'"],
        'style-src': ["'self'", "'unsafe-inline'"],  # Allow inline styles
        'connect-src': ["'self'"] + allowed_origins,
        'frame-ancestors': ["'none'"],  # Prevent iframe embedding
        'form-action': ["'self'"],
        'base-uri': ["'self'"],
    }
    csp_header = "; ".join([f"{key} {' '.join(value)}" for key, value in csp.items()])
    # Add security headers
    response.headers['Content-Security-Policy'] = csp_header
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # Only in production
    if os.environ.get('FLASK_ENV') == 'production':
        # Two years for HSTS
        response.headers['Strict-Transport-Security'] = 'max-age=63072000; includeSubDomains'
    return response

# Security improvement 7: Error handling
@app.errorhandler(404)
async def not_found_error(error):
    return jsonify({"error": "Resource not found", "status": 404}), 404

@app.errorhandler(500)
async def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({"error": "Internal server error", "status": 500}), 500

@app.errorhandler(403)
async def forbidden_error(error):
    return jsonify({"error": "Access forbidden", "status": 403}), 403

@app.errorhandler(429)
async def rate_limit_error(error):
    return jsonify({"error": "Rate limit exceeded. Please try again later.", "status": 429}), 429

# Root route for API server
@app.route('/')
async def api_root():
    """API server root - provide basic info"""
    logger.info("API root endpoint accessed")
    return jsonify({
        "status": "online",
        "message": "Discord Bot API Server",
        "server_time": datetime.utcnow().isoformat(),
        "endpoints": ["/api/auth", "/api/dashboard", "/api/bot"]
    })

# Health check endpoint
@app.route('/health')
@app.route('/api/health')  # Adding an additional route for flexibility
async def health_check():
    """API health check endpoint - used to verify server is up and running"""
    logger.debug("Health check endpoint accessed")
    return jsonify({
        "status": "ok",
        "time": datetime.utcnow().isoformat()
    })

# Root route for direct login redirects
@app.route('/login')
async def login_redirect():
    """Redirect /login requests to the proper auth endpoint"""
    logger.info("Login redirect accessed - forwarding to /api/auth/login")
    try:
        response = redirect('/api/auth/login')
        logger.info(f"Login redirect response created")
        return response
    except Exception as e:
        logger.error(f"Error in login redirect: {str(e)}", exc_info=True)
        return jsonify({"error": "Login redirect failed", "details": str(e)}), 500

@app.route('/callback')
async def callback_redirect():
    """Handle OAuth callback from Discord"""
    logger.info(f"Received OAuth callback at /callback with args: {dict(request.args)}")
    # Security improvement: Validate state parameter presence
    if 'state' not in request.args:
        logger.warning("OAuth callback missing state parameter - potential CSRF")
        return jsonify({"error": "Missing state parameter"}), 400
    # Forward all query parameters to the proper handler
    query_string = request.query_string.decode('utf-8')
    if query_string:
        redirect_url = f'/api/auth/callback?{query_string}'
        logger.info(f"Redirecting OAuth callback to: {redirect_url}")
        return redirect(redirect_url)
    return redirect('/api/auth/callback')

# Debug route to test CORS
@app.route('/api/debug/cors-test')
async def cors_test():
    """Simple endpoint to test CORS configuration"""
    logger.info("CORS test endpoint accessed")
    return jsonify({
        "status": "success",
        "message": "CORS is properly configured if you can see this message from your frontend",
        "headers": dict(request.headers)    
    })

# Import blueprints
try:
    from .dashboard_api import dashboard_bp
    from .auth_routes import auth_bp, register_blueprint as register_auth_bp
    from .debug import register_blueprint as register_debug_bp
    # Import our new middleware
    from .middleware import require_auth
    
    # Check if auth_debug is available
    has_auth_debug = False
    try:
        from .auth_debug import register_blueprint as register_auth_debug_bp
        has_auth_debug = True
    except ImportError:
        logger.info("Auth debug module not found. Debug endpoints will not be available.")

    # Register blueprints
    app.register_blueprint(dashboard_bp)
    register_auth_bp(app)
    register_debug_bp(app)
    
    if has_auth_debug:
        register_auth_debug_bp(app)
        
    logger.info("Successfully registered API blueprints")
except Exception as e:
    logger.error(f"Error initializing Quart application: {str(e)}", exc_info=True)

# Security improvement: Better initialization retries
max_retries = 5  # Increased retries
retry_delay = 2  # seconds

async def initialize_with_bot(bot_instance):
    """Initialize the API with a reference to the bot instance"""
    global bot_instance_ref
    bot_instance_ref = bot_instance

    # Store the bot instance in app config for easy access in routes
    app.config['BOT_INSTANCE'] = bot_instance
    
    # Initialize the API key manager with the bot instance
    # This allows the API key validation system to work properly
    app.config['API_KEY_MANAGER'] = api_key_manager
    logger.info("API key manager initialized and attached to app config")
    
    # Store the data service (ensure proper message_monitor access)
    db_connection = None
    success = False

    for attempt in range(max_retries):
        try:
            if bot_instance and hasattr(bot_instance, 'message_monitor') and bot_instance.message_monitor:
                logger.info(f"Attempt {attempt+1}/{max_retries}: Message monitor found on bot instance. Accessing database...")
                
                # Changed: Check if get_database method exists instead of looking for db_connection attribute
                if hasattr(bot_instance.message_monitor, 'get_database'):
                    logger.debug("Found get_database method on message_monitor")
                    db_connection = bot_instance.message_monitor.get_database()
                else:
                    # Fallback to other possible attribute names
                    logger.debug("No get_database method found, checking for database attribute")
                    if hasattr(bot_instance.message_monitor, 'database'):
                        db_connection = bot_instance.message_monitor.database
                    elif hasattr(bot_instance.message_monitor, 'db'):
                        db_connection = bot_instance.message_monitor.db

                if db_connection:
                    # Test the connection to ensure it's working
                    if hasattr(db_connection, 'test_connection'):
                        connection_valid = await db_connection.test_connection()
                        
                        if not connection_valid:
                            logger.warning(f"Database connection test failed on attempt {attempt+1}")
                            db_connection = None
                            continue

                    logger.info("Successfully obtained working database connection from message_monitor.")
                    app.config['DATA_SERVICE'] = db_connection
                    success = True
                    break
                else:
                    logger.warning(f"Attempt {attempt+1}/{max_retries}: Database connection is None.")
            else:
                logger.warning(f"Attempt {attempt+1}/{max_retries}: Message monitor not available.")
            
            if attempt < max_retries - 1:
                logger.info(f"Waiting {retry_delay} seconds before next attempt...")
                import asyncio
                await asyncio.sleep(retry_delay)
                # Exponential backoff
                retry_delay = min(retry_delay * 1.5, 10)
        except Exception as e:
            logger.error(f"Error during attempt {attempt+1}/{max_retries} to access database: {e}", exc_info=True)
            if attempt < max_retries - 1:
                logger.info(f"Waiting {retry_delay} seconds before next attempt...")
                import asyncio
                await asyncio.sleep(retry_delay)
                # Exponential backoff
                retry_delay = min(retry_delay * 1.5, 10)

    if not success:
        # Log detailed diagnostic information
        if not bot_instance:
            logger.warning("Bot instance is None. Data service not initialized.")
        elif not hasattr(bot_instance, 'message_monitor'):
            logger.warning("Bot instance does not have message_monitor attribute. Data service not initialized.")
        elif not bot_instance.message_monitor:
            logger.warning("Bot instance has message_monitor attribute but it's None. Data service not initialized.")
        else:
            # Log available attributes for debugging
            try:
                monitor_attrs = dir(bot_instance.message_monitor)
                logger.debug(f"Available MessageMonitor attributes: {monitor_attrs}")
            except Exception as e:
                logger.error(f"Error accessing MessageMonitor attributes: {e}")
            
            logger.warning("Message monitor exists but database access failed after multiple attempts.")
        
        # Only log this warning if we actually failed to initialize
        logger.warning("Data service not initialized. API endpoints will use mock data.")
        app.config['DATA_SERVICE'] = None
    
    # Check Discord OAuth credentials
    if not os.environ.get('DISCORD_CLIENT_ID') or not os.environ.get('DISCORD_CLIENT_SECRET'):
        logger.error("ERROR: Discord OAuth credentials are missing! DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET environment variables must be set.")
        logger.error("Users will not be able to log in until these credentials are configured.")

    # Initialize dashboard API (passing the full bot instance now)
    from .dashboard_api import initialize
    try:
        await initialize(bot_instance)
        logger.info("Successfully initialized dashboard API asynchronously")
    except Exception as e:
        logger.error(f"Error initializing dashboard API: {e}", exc_info=True)
    
    logger.info(f"API initialized with bot reference. Data service available: {success}")