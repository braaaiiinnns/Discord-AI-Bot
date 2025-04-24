#!/usr/bin/env python3
"""
Simple HTTP server for serving the dashboard static files.
This serves the dashboard separately from the API server.
"""

import os
import sys
import argparse
import http.server
import socketserver
import webbrowser
from urllib.parse import urlparse
import logging

# Add the project root to the path so we can import from there
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Set up logger
logger = logging.getLogger('discord_bot.dashboard')

# Get config values
try:
    from config.config import DASHBOARD_HOST, DASHBOARD_PORT, FLASK_SESSION_DIR
except ImportError:
    logger.warning("Could not import config. Using default values.")
    DASHBOARD_HOST = '127.0.0.1'
    DASHBOARD_PORT = 8080  # Updated default port to match config
    FLASK_SESSION_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data', 'flask_session')

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    """Custom request handler for the dashboard"""
    
    def __init__(self, *args, **kwargs):
        # Set the directory to serve files from
        dashboard_dir = os.path.dirname(os.path.abspath(__file__))
        super().__init__(*args, directory=dashboard_dir, **kwargs)
    
    def do_GET(self):
        """Handle GET requests"""
        # If path is '/' or empty, serve index.html
        if self.path == '/' or not self.path:
            self.path = '/index.html'
        elif self.path == '/dashboard':
            self.path = '/index.html'
        
        # Special case for /callback - handle OAuth2 callback
        if self.path.startswith('/callback'):
            # Get the API server URL from js/config.js (default to localhost:5000)
            api_server_url = self.get_api_server_url()
            
            # Redirect to the API server's callback endpoint
            self.send_response(302)
            redirect_url = f"{api_server_url}/callback{self.path[9:]}"  # Remove '/callback' prefix
            self.send_header('Location', redirect_url)
            self.end_headers()
            return
        
        # Handle standard GET request
        try:
            return super().do_GET()
        except BrokenPipeError:
            # Client disconnected, log it and continue
            logger.debug("Client disconnected while serving file")
            return
        except ConnectionResetError:
            # Connection was reset, log it and continue
            logger.debug("Connection was reset by client")
            return
        except Exception as e:
            # Log other exceptions but don't crash
            logger.error(f"Error serving file: {str(e)}")
            return
    
    def copyfile(self, source, outputfile):
        """Override copyfile to handle broken pipe errors gracefully"""
        try:
            super().copyfile(source, outputfile)
        except BrokenPipeError:
            logger.debug("Client disconnected during file transfer")
        except ConnectionResetError:
            logger.debug("Connection reset during file transfer")
        except Exception as e:
            logger.error(f"Error during file transfer: {str(e)}")
    
    def get_api_server_url(self):
        """Extract API server URL from config.js"""
        try:
            # Default API URL
            api_url = "http://localhost:5000"
            
            # Try to read from config.js
            config_path = os.path.join(self.directory, 'js', 'config.js')
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    for line in f:
                        if 'apiBaseUrl:' in line and 'window.location' not in line:
                            # Extract hardcoded API URL if present
                            parts = line.split(':', 1)[1].strip().strip(',').strip("'").strip('"')
                            if parts.startswith('http'):
                                api_url = parts
                                # Remove /api suffix if present
                                if api_url.endswith('/api'):
                                    api_url = api_url[:-4]
            
            return api_url
        except Exception as e:
            logger.error(f"Error getting API server URL: {e}")
            return "http://localhost:5000"  # Default fallback
    
    def log_message(self, format, *args):
        """Override to customize logging format"""
        logger.info(f"{self.address_string()} - {format % args}")

def start_dashboard_server(host='127.0.0.1', port=8080, open_browser=True):
    """Start the dashboard HTTP server"""
    try:
        # Create the server
        handler = DashboardHandler
        
        # Try to create server, incrementing port if needed
        while True:
            try:
                httpd = socketserver.TCPServer((host, port), handler)
                break
            except OSError as e:
                if "Address already in use" in str(e):
                    logger.warning(f"Port {port} is already in use. Trying port {port + 1}.")
                    port += 1
                else:
                    raise
        
        # Always use 'localhost' in the URL instead of IP address for browser opening
        server_url = f"http://localhost:{port}"
        
        logger.info(f"Starting dashboard server at {server_url}")
        logger.info("Note: This is just a static file server. The API server must be running separately.")
        
        # Open the browser if requested
        if open_browser:
            webbrowser.open(server_url)
        
        # Start the server
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("\nDashboard server stopped")
    except OSError as e:
        if "Address already in use" in str(e):
            logger.error(f"Error: Port {port} is already in use. Try a different port.")
        else:
            logger.error(f"Error starting dashboard server: {e}")
    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Dashboard Server for Discord Bot")
    parser.add_argument('--host', default=DASHBOARD_HOST, help=f'Host to bind server to (default: {DASHBOARD_HOST})')
    parser.add_argument('--port', type=int, default=DASHBOARD_PORT, help=f'Port to bind server to (default: {DASHBOARD_PORT})')
    parser.add_argument('--no-browser', action='store_true', help="Don't open browser automatically")
    
    args = parser.parse_args()
    
    # Start the server
    start_dashboard_server(args.host, args.port, not args.no_browser)