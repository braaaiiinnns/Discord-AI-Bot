"""
Session handling module for Discord OAuth2 authentication.
This module handles session management, Redis integration, and fixes byte/string conversion issues.
"""

import os
import logging
import asyncio
import redis
import uuid
from datetime import datetime, timedelta
from quart.sessions import SecureCookieSessionInterface
from itsdangerous import Signer, BadSignature, want_bytes

# Set up logger
logger = logging.getLogger('discord_bot.api.session_handler')

class AsyncRedisWrapper:
    """A wrapper around redis-py that makes it compatible with quart_session's async expectations"""
    
    def __init__(self, redis_client):
        self.client = redis_client
        
    async def get(self, key):
        """Async wrapper for Redis GET"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.client.get(key))
    
    async def set(self, key, value):
        """Async wrapper for Redis SET"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.client.set(key, value))
    
    async def setex(self, name, time, value):
        """Async wrapper for Redis SETEX with correct parameter order"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.client.setex(name, time, value))
    
    async def delete(self, key):
        """Async wrapper for Redis DELETE"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.client.delete(key))
    
    async def ping(self):
        """Async wrapper for Redis PING"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.client.ping())

class FixedSessionInterface:
    """Wrapper for session interface to ensure proper byte/string conversion"""
    
    def __init__(self, app):
        self.original_interface = app.session_interface
        self.secure_cookie_fallback = SecureCookieSessionInterface()
        
        # Store these for direct access
        self.key_prefix = getattr(self.original_interface, 'key_prefix', 'session:')
        self.use_signer = getattr(self.original_interface, 'use_signer', False)
        
    async def open_session(self, app, request):
        try:
            # Get session ID from cookie
            cookie_name = app.config.get('SESSION_COOKIE_NAME', 'session')
            sid = request.cookies.get(cookie_name)
            
            if not sid:
                # Create a new session if no session ID exists
                from quart_session.sessions import ServerSideSession
                session_class = getattr(self.original_interface, 'session_class', ServerSideSession)
                return session_class(sid=self._generate_sid())
                
            # Handle signed session IDs
            if self.use_signer:
                try:
                    signer = self._get_signer(app)
                    if signer is not None:
                        # If the sid is bytes, keep it as bytes for unsigning
                        if isinstance(sid, str):
                            sid_for_signature = sid.encode('utf-8')
                        else:
                            sid_for_signature = sid
                            
                        try:
                            sid_bytes = signer.unsign(sid_for_signature)
                            sid = sid_bytes.decode('utf-8')
                        except BadSignature:
                            # Log more details for diagnostic purposes
                            app.logger.warning(f"Bad signature for sid: {sid[:30]}... (truncated)")
                            # Add additional info if possible to help diagnose the issue
                            try:
                                if len(sid) > 100:
                                    app.logger.debug(f"Session ID is unusually long ({len(sid)} chars)")
                                # Log timestamp to help correlate with other logs
                                from datetime import datetime
                                app.logger.debug(f"Bad signature detected at {datetime.now().isoformat()}")
                            except Exception:
                                pass
                            # Create a new session with a new ID
                            from quart_session.sessions import ServerSideSession
                            session_class = getattr(self.original_interface, 'session_class', ServerSideSession)
                            return session_class(sid=self._generate_sid())
                except Exception as e:
                    app.logger.error(f"Error unsigning session ID: {e}")
                    # Fall back to secure cookie session
                    return await self.secure_cookie_fallback.open_session(app, request)
            
            # Get the session data
            try:
                if hasattr(self.original_interface, 'get'):
                    # Get the session data from the backend
                    session_key = self.key_prefix + sid
                    val = await self.original_interface.get(key=session_key, app=app)
                    
                    if val is None:
                        # Session doesn't exist or has expired
                        from quart_session.sessions import ServerSideSession
                        session_class = getattr(self.original_interface, 'session_class', ServerSideSession)
                        return session_class(sid=self._generate_sid())
                    
                    # Deserialize the session data
                    if hasattr(self.original_interface, 'serializer') and self.original_interface.serializer:
                        try:
                            data = self.original_interface.serializer.loads(val)
                        except (ValueError, TypeError) as e:
                            app.logger.warning(f"Failed to deserialize session data for sid: {sid}: {e}")
                            from quart_session.sessions import ServerSideSession
                            session_class = getattr(self.original_interface, 'session_class', ServerSideSession)
                            return session_class(sid=self._generate_sid())
                    else:
                        data = val
                    
                    # Create the session object
                    from quart_session.sessions import ServerSideSession
                    session_class = getattr(self.original_interface, 'session_class', ServerSideSession)
                    return session_class(data, sid)
            except Exception as e:
                app.logger.error(f"Error retrieving session data: {e}")
            
            # Fall back to the original interface if our custom implementation fails
            return await self.original_interface.open_session(app, request)
        except Exception as e:
            app.logger.error(f"Error in open_session: {str(e)}")
            # Fall back to secure cookie session as a last resort
            return await self.secure_cookie_fallback.open_session(app, request)
    
    async def save_session(self, app, session, response):
        try:
            # Don't save unmodified sessions
            if hasattr(session, 'modified') and not session.modified:
                return
            
            cookie_name = app.config.get('SESSION_COOKIE_NAME', 'session')
            domain = self.get_cookie_domain(app)
            path = self.get_cookie_path(app)
            
            # If the session is empty, delete it
            if not session:
                if hasattr(session, 'sid'):
                    session_key = self.key_prefix + session.sid
                    try:
                        if hasattr(self.original_interface, 'delete'):
                            await self.original_interface.delete(key=session_key, app=app)
                    except Exception as e:
                        app.logger.error(f"Error deleting session: {e}")
                
                response.delete_cookie(cookie_name, domain=domain, path=path)
                return
            
            # Get cookie parameters
            httponly = self.get_cookie_httponly(app)
            secure = self.get_cookie_secure(app)
            samesite = self.get_cookie_samesite(app)
            expires = self.get_expiration_time(app, session)
            
            # Serialize and save session data
            if hasattr(session, 'sid'):
                session_key = self.key_prefix + session.sid
                
                try:
                    # Serialize the session data
                    if hasattr(self.original_interface, 'serializer') and self.original_interface.serializer:
                        val = self.original_interface.serializer.dumps(dict(session))
                    else:
                        val = dict(session)
                    
                    # Save the session data
                    if hasattr(self.original_interface, 'set'):
                        await self.original_interface.set(key=session_key, value=val, app=app)
                    
                    # Sign the session ID if needed
                    if self.use_signer:
                        signer = self._get_signer(app)
                        if signer is not None:
                            # Ensure sid is bytes before signing
                            if isinstance(session.sid, str):
                                sid_bytes = session.sid.encode('utf-8')
                            else:
                                sid_bytes = session.sid
                            
                            # Sign and ensure the result is a string
                            session_id = signer.sign(sid_bytes).decode('utf-8')
                        else:
                            session_id = session.sid
                    else:
                        session_id = session.sid
                    
                    # Ensure session_id is a string before setting the cookie
                    if isinstance(session_id, bytes):
                        session_id = session_id.decode('utf-8')
                    
                    # Set the cookie
                    response.set_cookie(
                        cookie_name, 
                        session_id,
                        expires=expires,
                        httponly=httponly,
                        domain=domain,
                        path=path,
                        secure=secure,
                        samesite=samesite
                    )
                    return
                except Exception as e:
                    app.logger.error(f"Error in custom save_session implementation: {e}")
            
            # Fall back to original interface if our implementation fails
            return await self.original_interface.save_session(app, session, response)
        except Exception as e:
            app.logger.error(f"Error in save_session: {str(e)}")
            # Fall back to secure cookie session as a last resort
            try:
                return await self.secure_cookie_fallback.save_session(app, session, response)
            except Exception as e:
                app.logger.error(f"Error in fallback save_session: {str(e)}")
            
    async def create(self, app):
        """Delegate the create method to the original interface if it exists"""
        try:
            if hasattr(self.original_interface, 'create'):
                return await self.original_interface.create(app)
        except Exception as e:
            app.logger.error(f"Error in create method: {str(e)}")
        return None
        
    def is_null_session(self, session):
        """Check if a session is null by delegating to the original interface"""
        try:
            if hasattr(self.original_interface, 'is_null_session'):
                return self.original_interface.is_null_session(session)
            else:
                # Default implementation similar to SecureCookieSessionInterface
                return session.new and not session
        except Exception as e:
            logger.error(f"Error in is_null_session method: {str(e)}")
            # Fallback implementation
            return True
            
    def get_cookie_domain(self, app):
        """Get the cookie domain setting"""
        if hasattr(self.original_interface, 'get_cookie_domain'):
            return self.original_interface.get_cookie_domain(app)
        return app.config.get('SESSION_COOKIE_DOMAIN')
    
    def get_cookie_path(self, app):
        """Get the cookie path setting"""
        if hasattr(self.original_interface, 'get_cookie_path'):
            return self.original_interface.get_cookie_path(app)
        return app.config.get('SESSION_COOKIE_PATH', '/')
    
    def get_cookie_httponly(self, app):
        """Get the cookie httponly setting"""
        if hasattr(self.original_interface, 'get_cookie_httponly'):
            return self.original_interface.get_cookie_httponly(app)
        return app.config.get('SESSION_COOKIE_HTTPONLY', True)
    
    def get_cookie_secure(self, app):
        """Get the cookie secure setting"""
        if hasattr(self.original_interface, 'get_cookie_secure'):
            return self.original_interface.get_cookie_secure(app)
        return app.config.get('SESSION_COOKIE_SECURE', False)
    
    def get_cookie_samesite(self, app):
        """Get the cookie samesite setting"""
        if hasattr(self.original_interface, 'get_cookie_samesite'):
            return self.original_interface.get_cookie_samesite(app)
        return app.config.get('SESSION_COOKIE_SAMESITE', 'Lax')
    
    def get_expiration_time(self, app, session):
        """Get session expiration time"""
        if hasattr(self.original_interface, 'get_expiration_time'):
            return self.original_interface.get_expiration_time(app, session)
        if session.permanent:
            return datetime.now() + app.permanent_session_lifetime
        return None
    
    def _generate_sid(self):
        """Generate a new session ID"""
        return str(uuid.uuid4())
        
    def _get_signer(self, app):
        """Get a signer for session signing"""
        if not app.secret_key:
            return None
        return Signer(app.secret_key, salt='quart-session', key_derivation='hmac')

def setup_session_handler(app, flask_session_dir):
    """Initialize and configure session handling for the application
    
    Args:
        app: The Quart application instance
        flask_session_dir: Directory path for filesystem session storage (fallback)
        
    Returns:
        None
    """
    # Configure session settings
    app.config['SESSION_PERMANENT'] = True
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)  # Adjust as needed
    
    # Enhance cookie security
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('PRODUCTION', 'false').lower() == 'true'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_USE_SIGNER'] = True
    
    # Try to connect to Redis
    try:
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        redis_client = redis.from_url(redis_url)
        # Test the connection synchronously
        redis_client.ping()
        # Wrap the client to make it compatible with quart_session
        wrapped_client = AsyncRedisWrapper(redis_client)
        logger.info(f"Successfully connected to Redis at {redis_url}")
        app.config['SESSION_REDIS'] = wrapped_client
        
        # Schedule periodic cleanup of expired sessions
        _schedule_session_cleanup(app, redis_client)
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {str(e)}. Using filesystem session fallback.")
        # Fallback to filesystem session if Redis is unavailable
        app.config['SESSION_TYPE'] = 'filesystem'
        app.config['SESSION_FILE_DIR'] = flask_session_dir
        app.config['SESSION_FILE_THRESHOLD'] = 500  # Maximum number of sessions stored as files
        
        # Schedule filesystem session cleanup
        _schedule_filesystem_cleanup(flask_session_dir)

    # Initialize Quart-Session with proper error handling
    try:
        from quart_session import Session
        Session(app)
        # Apply our fix to handle byte/string conversion issues
        app.session_interface = FixedSessionInterface(app)
        logger.info("Session interface initialized successfully with byte/string handling fixes")
    except Exception as e:
        logger.error(f"Error initializing session interface: {str(e)}")
        app.session_interface = SecureCookieSessionInterface()
        logger.warning("Falling back to SecureCookieSessionInterface due to session initialization error")
        
    # Ensure session directory exists (for filesystem fallback)
    os.makedirs(flask_session_dir, exist_ok=True)
    logger.info(f"Using session directory (fallback): {flask_session_dir}")
    logger.info(f"Session backend: {app.config.get('SESSION_TYPE', 'unknown')}")

def _schedule_session_cleanup(app, redis_client):
    """Schedule periodic cleanup of expired Redis sessions"""
    try:
        import threading
        
        def cleanup_redis_sessions():
            try:
                # Run SCAN to find expired sessions
                cursor = 0
                session_prefix = app.config.get('SESSION_KEY_PREFIX', 'session:')
                pattern = f"{session_prefix}*"
                
                while True:
                    cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=100)
                    for key in keys:
                        if not redis_client.ttl(key):
                            redis_client.delete(key)
                            logger.debug(f"Removed expired session: {key}")
                    
                    if cursor == 0:
                        break
                        
                logger.info("Completed Redis session cleanup")
            except Exception as e:
                logger.error(f"Error during Redis session cleanup: {e}")
            
            # Schedule the next cleanup
            cleanup_timer = threading.Timer(86400, cleanup_redis_sessions)  # Run daily
            cleanup_timer.daemon = True
            cleanup_timer.start()
        
        # Start the initial cleanup
        initial_timer = threading.Timer(3600, cleanup_redis_sessions)  # Start after 1 hour
        initial_timer.daemon = True
        initial_timer.start()
        logger.info("Scheduled Redis session cleanup")
    except Exception as e:
        logger.error(f"Failed to schedule Redis session cleanup: {e}")

def _schedule_filesystem_cleanup(session_dir):
    """Schedule cleanup of expired filesystem sessions"""
    try:
        import threading
        import os
        import time
        
        def cleanup_filesystem_sessions():
            try:
                now = time.time()
                expiry = 86400  # 24 hours
                count = 0
                
                for filename in os.listdir(session_dir):
                    file_path = os.path.join(session_dir, filename)
                    if os.path.isfile(file_path):
                        file_age = now - os.path.getmtime(file_path)
                        if file_age > expiry:
                            os.remove(file_path)
                            count += 1
                
                logger.info(f"Removed {count} expired filesystem sessions")
            except Exception as e:
                logger.error(f"Error during filesystem session cleanup: {e}")
            
            # Schedule the next cleanup
            cleanup_timer = threading.Timer(86400, cleanup_filesystem_sessions)  # Run daily
            cleanup_timer.daemon = True
            cleanup_timer.start()
        
        # Start the initial cleanup
        initial_timer = threading.Timer(3600, cleanup_filesystem_sessions)  # Start after 1 hour
        initial_timer.daemon = True
        initial_timer.start()
        logger.info("Scheduled filesystem session cleanup")
    except Exception as e:
        logger.error(f"Failed to schedule filesystem session cleanup: {e}")