import logging
import os
from logging.handlers import RotatingFileHandler

# ANSI color codes for terminal coloring
class Colors:
    RESET = "\033[0m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    BOLD_RED = "\033[1;31m"
    BLUE = "\033[34m"  # Added for INFO
    GREEN = "\033[32m" # Added for DEBUG

class ColoredFormatter(logging.Formatter):
    """
    A custom formatter that adds colors based on the log level.
    """
    # Define the format string with timestamp
    FORMAT = "%(asctime)s - %(levelname)s: %(message)s"
    DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

    LEVEL_COLORS = {
        logging.DEBUG: Colors.GREEN,
        logging.INFO: Colors.BLUE,
        logging.WARNING: Colors.YELLOW,
        logging.ERROR: Colors.RED,
        logging.CRITICAL: Colors.BOLD_RED,
    }

    def __init__(self, fmt=FORMAT, datefmt=DATE_FORMAT, style='%'):
        super().__init__(fmt=fmt, datefmt=datefmt, style=style)

    def format(self, record):
        # Get color for the log level
        color = self.LEVEL_COLORS.get(record.levelno, Colors.RESET)
        
        # Apply the formatting logic of the parent class
        log_fmt = self.FORMAT # Use the defined format
        formatter = logging.Formatter(log_fmt, datefmt=self.DATE_FORMAT)
        formatted_message = formatter.format(record)
        
        # Apply color to the entire formatted message
        return f"{color}{formatted_message}{Colors.RESET}"

def setup_logger(name='discord_bot', log_file=None, level=logging.WARNING):
    """
    Set up a logger with both file and console output.
    
    Args:
        name (str): Name of the logger
        log_file (str): Path to log file
        level (int): Logging level
        
    Returns:
        logging.Logger: Configured logger
    """
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    # Use print for initial setup debugging as logger might not be fully ready
    print(f"[DEBUG_SETUP] Logger '{name}' level set to: {logging.getLevelName(logger.level)} (Input: {logging.getLevelName(level)})", flush=True)
    
    # Clear any existing handlers to prevent duplication
    if logger.hasHandlers():
        print("[DEBUG_SETUP] Clearing existing handlers.", flush=True)
        logger.handlers = []
    
    # Prevent propagation to avoid duplicate logs
    logger.propagate = False
    print("[DEBUG_SETUP] Disabled logger propagation.", flush=True)
    
    # Create colored formatter for console output
    color_formatter = ColoredFormatter()
    print("[DEBUG_SETUP] Created colored formatter for console.", flush=True)
    
    # Create console handler with colored output
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    print(f"[DEBUG_SETUP] Console handler level set to: {logging.getLevelName(console_handler.level)}", flush=True)
    console_handler.setFormatter(color_formatter)
    
    # Add the handler to the logger
    logger.addHandler(console_handler)
    print("[DEBUG_SETUP] Added console handler to logger.", flush=True)
    
    # Create file handler if log_file is provided
    if log_file:
        print(f"[DEBUG_SETUP] Log file specified: {log_file}", flush=True)
        # Create standard formatter for file logs (no colors)
        std_formatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s', 
                                      datefmt='%Y-%m-%d %H:%M:%S')
        print("[DEBUG_SETUP] Created standard formatter for file.", flush=True)
        
        # Create directory if it doesn't exist
        log_dir = os.path.dirname(log_file)
        try:
            if not os.path.exists(log_dir):
                print(f"[DEBUG_SETUP] Log directory '{log_dir}' does not exist. Creating.", flush=True)
                os.makedirs(log_dir, exist_ok=True)
            else:
                print(f"[DEBUG_SETUP] Log directory '{log_dir}' already exists.", flush=True)
        except OSError as e:
            # Use temporary print as logger might not be fully configured for file yet
            print(f"ERROR: Could not create log directory '{log_dir}': {e}", flush=True)
            # Fallback: Don't add file handler if directory creation fails
            log_file = None 

        if log_file: # Check again in case directory creation failed
            # Setup rotating file handler (10MB max size, keep 5 backups)
            file_handler = RotatingFileHandler(
                log_file, 
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(std_formatter)
            print(f"[DEBUG_SETUP] Created rotating file handler with level {logging.getLevelName(level)}, maxBytes=10MB, backupCount=5.", flush=True)
            
            # Add the handler to the logger
            logger.addHandler(file_handler)
            print("[DEBUG_SETUP] Added file handler to logger.", flush=True)
    else:
        print("[DEBUG_SETUP] No log file specified. Skipping file handler setup.", flush=True)
    
    # Disable specific loggers that are known to cause duplication
    for logger_name in ['discord', 'discord.gateway', 'werkzeug']:
        log = logging.getLogger(logger_name)
        log.setLevel(logging.ERROR) # Keep this as ERROR
        log.propagate = False
        print(f"[DEBUG_SETUP] Set level=ERROR and disabled propagation for logger '{logger_name}'.", flush=True)
    
    print(f"[DEBUG_SETUP] Logger '{name}' setup complete.", flush=True)
    return logger
