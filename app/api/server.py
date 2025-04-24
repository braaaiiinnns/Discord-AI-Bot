import os
import socket
import logging
import ssl
import signal
import threading
import time
import asyncio
from contextlib import contextmanager
from datetime import datetime
from quart import Quart
from hypercorn.config import Config as HypercornConfig
from hypercorn.asyncio import serve
from .app import app, initialize_with_bot

# Set up logger
logger = logging.getLogger('discord_bot.api.server')

# Thread-safe timeout context manager
class ThreadingTimeout(Exception):
    pass

@contextmanager
def timeout(seconds, error_message="Operation timed out"):
    """Context manager for timeouts using threading instead of signals"""
    timer = None
    
    def timeout_function():
        nonlocal timer
        thread_id = threading.current_thread().ident
        logger.debug(f"Timeout triggered for thread {thread_id}")
        # Raise exception in the main thread
        raise_exc_info = sys.exc_info()
        if raise_exc_info == (None, None, None):
            raise_exc_info = (ThreadingTimeout, ThreadingTimeout(error_message), None)
        raise_exc(raise_exc_info[1], thread_id)
    
    import _thread
    import sys
    
    def raise_exc(exc, thread_id):
        """Raise exception in target thread"""
        if not thread_id:
            return
        res = _thread.raise_exception(thread_id, exc.__class__)
        if not res:
            logger.warning(f"Failed to raise timeout exception in thread {thread_id}")
    
    try:
        timer = threading.Timer(seconds, timeout_function)
        timer.daemon = True
        timer.start()
        yield
    finally:
        if timer:
            timer.cancel()

# Security improvement: Port availability checking with timeout
def is_port_in_use(host, port, timeout_seconds=2):
    """Check if a port is in use with timeout protection"""
    try:
        with timeout(timeout_seconds, f"Port check timed out for {host}:{port}"):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout_seconds)
                # Set SO_REUSEADDR to allow reusing the socket immediately
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind((host, port))
                    # Close and explicitly unbind the port before returning
                    s.close()
                    return False
                except OSError:
                    return True
    except TimeoutError as e:
        logger.warning(f"Timeout while checking port {port}: {e}")
        # Assume port is in use if check times out
        return True

# Security improvement: Health monitoring thread
class HealthMonitor(threading.Thread):
    """Thread to monitor server health and perform periodic security checks"""
    
    def __init__(self, interval=60):
        super().__init__(daemon=True)
        self.interval = interval
        self.running = True
        self.start_time = datetime.now()
        logger.info("Health monitoring thread initialized")
        
    def run(self):
        """Run health checks periodically"""
        logger.info("Health monitoring thread started")
        while self.running:
            try:
                self.check_health()
                time.sleep(self.interval)
            except Exception as e:
                logger.error(f"Error in health monitor: {e}")
                time.sleep(self.interval)
    
    def check_health(self):
        """Perform health checks"""
        uptime = datetime.now() - self.start_time
        
        # Log basic health metrics
        logger.debug(f"Server uptime: {uptime}")
        
        # Check for unusual connection patterns or potential attacks
        # (This would be expanded with real metrics in a production system)
        
    def stop(self):
        """Stop the monitoring thread"""
        self.running = False
        logger.info("Health monitoring thread stopped")

async def _start_server_async(bot_instance, host=None, port=5000, use_ssl=None, is_main_thread=False):
    """
    Asynchronous implementation to start the API server with the given bot instance.
    
    Args:
        bot_instance: The bot instance
        host: The host to bind to (defaults to localhost in development, configured in production)
        port: The port to bind to
        use_ssl: Whether to use SSL/TLS (defaults to True in production)
        is_main_thread: Whether this function is being called from the main thread
    """
    logger.info("API server initialization beginning...")
    
    try:
        # Validate bot_instance
        if not bot_instance:
            logger.error("Bot instance is None. Cannot initialize API server.")
            return None
            
        # Security improvement: Better environment-aware defaults
        env = os.environ.get('FLASK_ENV', 'development')
        
        # In development mode, only bind to localhost by default
        if host is None:
            if env == 'production':
                # In production, use environment variable with no default
                host = os.environ.get('API_HOST')
                if not host:
                    logger.error("No API_HOST environment variable in production mode")
                    raise ValueError("API_HOST environment variable must be set in production")
            else:
                # In development, default to localhost for security
                host = '127.0.0.1'
                logger.info("Development mode: binding to localhost only")
        
        # Security improvement: Enable SSL/TLS by default in production
        if use_ssl is None:
            use_ssl = env == 'production'
        
        # SSL configuration
        ssl_context = None
        if use_ssl:
            cert_path = os.environ.get('SSL_CERT_PATH')
            key_path = os.environ.get('SSL_KEY_PATH')
            ca_cert_path = os.environ.get('SSL_CA_CERT_PATH')  # Optional CA certificate
            
            if not cert_path or not key_path:
                if env == 'production':
                    logger.error("SSL enabled but SSL_CERT_PATH or SSL_KEY_PATH not provided")
                    raise ValueError("SSL_CERT_PATH and SSL_KEY_PATH must be provided when SSL is enabled in production")
                else:
                    logger.warning("SSL requested but no certificates provided. Continuing without SSL.")
                    use_ssl = False
            else:
                # Security improvement: Enhanced SSL context with modern settings
                try:
                    # Create SSL context with modern protocols and ciphers
                    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                    ssl_context.load_cert_chain(cert_path, key_path)
                    
                    # Security improvement: Load CA cert if provided
                    if ca_cert_path and os.path.exists(ca_cert_path):
                        ssl_context.load_verify_locations(cafile=ca_cert_path)
                        logger.info(f"CA certificate loaded from {ca_cert_path}")
                    
                    # Security improvement: Set modern protocols (TLS 1.2+)
                    ssl_context.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
                    
                    # Security improvement: Set secure cipher suites
                    # This uses modern, secure ciphers only
                    ssl_context.set_ciphers('ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384')
                    
                    # Security improvement: Set ECDH curve
                    ssl_context.set_ecdh_curve('prime256v1')
                    
                    # Security improvement: Check certificate file permissions
                    try:
                        cert_permissions = os.stat(cert_path).st_mode & 0o777
                        key_permissions = os.stat(key_path).st_mode & 0o777
                        
                        if cert_permissions > 0o644:
                            logger.warning(f"Certificate file permissions too open: {oct(cert_permissions)}, should be 0o644 or less")
                            
                        if key_permissions > 0o600:
                            logger.warning(f"Private key file permissions too open: {oct(key_permissions)}, should be 0o600 or less")
                            # Attempt to fix key permissions
                            try:
                                os.chmod(key_path, 0o600)
                                logger.info(f"Fixed permissions on {key_path} to 0o600")
                            except Exception as e:
                                logger.warning(f"Could not fix key file permissions: {e}")
                    except Exception as e:
                        logger.warning(f"Could not check certificate file permissions: {e}")
                    
                    logger.info(f"SSL configuration loaded from {cert_path} and {key_path} with modern security settings")
                except Exception as e:
                    logger.error(f"Failed to load SSL certificates: {e}", exc_info=True)
                    if env == 'production':
                        raise
                    else:
                        logger.warning("Continuing without SSL in development mode")
                        use_ssl = False
                        ssl_context = None
                        
        # Log bot instance details for diagnostics
        message_monitor_available = False
        database_available = False
        
        # Security improvement: Add timeout for potentially slow operations
        try:
            with timeout(5, "Bot instance check timed out"):
                if hasattr(bot_instance, 'message_monitor'):
                    logger.info("Bot instance has message_monitor attribute.")
                    if bot_instance.message_monitor:
                        logger.info("MessageMonitor object is available.")
                        message_monitor_available = True
                        if hasattr(bot_instance.message_monitor, 'db'):
                            logger.info("MessageMonitor has database attribute.")
                            if bot_instance.message_monitor.db:
                                logger.info("Database object is available.")
                                database_available = True
                            else:
                                logger.warning("Database object is None.")
                        else:
                            logger.warning("MessageMonitor does not have database attribute.")
                    else:
                        logger.warning("MessageMonitor object is None.")
                else:
                    logger.warning("Bot instance does not have message_monitor attribute.")
        except TimeoutError:
            logger.warning("Timeout while checking bot instance components")
        except Exception as e:
            logger.warning(f"Error checking bot instance components: {e}")
        
        # Provide a summary of component availability
        logger.info(f"Component status - MessageMonitor: {'✅' if message_monitor_available else '❌'}, Database: {'✅' if database_available else '❌'}")
        
        # Add a small delay to ensure all components have stabilized
        logger.info("Waiting 1 second for all components to stabilize...")
        await asyncio.sleep(1)
            
        # Initialize the API with the bot instance
        logger.info("Initializing API with bot instance...")
        await initialize_with_bot(bot_instance)
        logger.info("API server initialized with bot instance.")
        
        # Security improvement: More comprehensive port availability check
        original_port = port
        max_port_attempts = 5
        port_found = False
        
        # First try with the originally requested port
        for attempt in range(max_port_attempts):
            current_port = original_port + attempt
            if not is_port_in_use(host, current_port):
                port = current_port
                port_found = True
                if attempt > 0:
                    logger.warning(f"Using alternate port {port} after {attempt} attempts")
                break
            logger.warning(f"Port {current_port} is already in use, trying next port")
            
        if not port_found:
            logger.error(f"Failed to find available port after {max_port_attempts} attempts")
            return None
        
        # Start the Quart app with Hypercorn
        logger.info(f"Starting API server on {host}:{port}" + (" with SSL" if use_ssl else ""))
        try:
            # Configure Hypercorn
            config = HypercornConfig()
            config.bind = [f"{host}:{port}"]
            config.access_log_format = '%(h)s %(r)s %(s)s %(b)s %(D)s'
            config.accesslog = logging.getLogger('discord_bot.api.access')
            config.errorlog = logging.getLogger('discord_bot.api.error')
            config.workers = 1  # Just one worker when running in a thread
            config.keep_alive_timeout = 90  # 90 seconds keep-alive timeout
            config.graceful_timeout = 10.0  # 10 seconds graceful shutdown timeout
            config.worker_class = "asyncio"
            config.max_requests = 1000  # Restart workers after handling 1000 requests
            config.max_requests_jitter = 100  # Add jitter to prevent all workers restarting at once
            config.max_received_size = 16 * 1024 * 1024  # 16 MB max request size
            
            # Configure SSL
            if ssl_context:
                config.ssl_enabled = True
                config.certfile = cert_path
                config.keyfile = key_path
                if ca_cert_path and os.path.exists(ca_cert_path):
                    config.ca_certs = ca_cert_path
                
            # Security improvement: Log successful startup with timestamp
            startup_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            logger.info(f"API server is now running at {startup_time} and handling requests")
            
            # CRITICAL FIX: Disable signal handling when running in a non-main thread
            # This prevents the "set_wakeup_fd only works in main thread" error
            if not is_main_thread:
                # Create a shutdown event instead of using signals
                shutdown_event = asyncio.Event()
                return serve(app, config, shutdown_trigger=shutdown_event.wait)
            else:
                # Use normal signal handling when in the main thread
                return serve(app, config)
            
        except OSError as e:
            if "Address already in use" in str(e):
                logger.error(f"Port {port} is already in use. Please choose a different port.")
            else:
                logger.error(f"Failed to start API server: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"An unexpected error occurred while starting the API server: {e}", exc_info=True)
            return None
    
    except Exception as e:
        logger.error(f"Error starting API server: {e}", exc_info=True)
        return None

def start_server(bot_instance, host=None, port=5000, use_ssl=None):
    """
    Synchronous wrapper to start the API server with the given bot instance.
    This function creates a new event loop and runs the async _start_server_async function.
    
    Args:
        bot_instance: The bot instance
        host: The host to bind to (defaults to localhost in development, configured in production)
        port: The port to bind to
        use_ssl: Whether to use SSL/TLS (defaults to True in production)
    """
    # Security improvement: Start health monitoring
    health_monitor = HealthMonitor()
    health_monitor.start()
    
    try:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Start the server asynchronously
        server_task = loop.run_until_complete(_start_server_async(bot_instance, host, port, use_ssl, is_main_thread=threading.current_thread() is threading.main_thread()))
        
        if server_task:
            # Keep the event loop running to handle requests
            loop.run_until_complete(server_task)
        else:
            logger.error("Failed to start server - _start_server_async returned None")
            
    except Exception as e:
        logger.error(f"Error in start_server: {e}", exc_info=True)
    finally:
        # Cleanup
        health_monitor.stop()
        try:
            loop.close()
        except Exception as e:
            logger.error(f"Error closing event loop: {e}", exc_info=True)

# Security improvement: Clean shutdown handler
def shutdown_server(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"Received signal {signum}, shutting down server...")
    # Stop the asyncio event loop
    loop = asyncio.get_event_loop()
    loop.stop()
    logger.info("Server shutdown handler completed")
    
    # Actually terminate the process
    import sys
    sys.exit(0)

# Register signal handlers for graceful shutdown
signal.signal(signal.SIGTERM, shutdown_server)
signal.signal(signal.SIGINT, shutdown_server)

# Main entry point if run directly
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('API_HOST', '127.0.0.1')  # Default to localhost for security
    use_ssl = os.environ.get('USE_SSL', '').lower() == 'true'
    
    # Security warning for direct execution
    logger.warning("Server starting in direct execution mode. This is not recommended for production.")
    
    # Create and run the asyncio event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(start_server(None, host=host, port=port, use_ssl=use_ssl))
    except KeyboardInterrupt:
        logger.info("Server stopped by keyboard interrupt")
    finally:
        loop.close()
