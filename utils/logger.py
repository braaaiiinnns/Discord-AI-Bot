import logging
import os
from logging.handlers import RotatingFileHandler
from colorama import Fore, Style

def setup_logger():
    logger = logging.getLogger('discord_bot')
    logger.setLevel(logging.DEBUG)
    
    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    
    # Use an absolute path for the log file
    log_file_path = os.path.join(logs_dir, 'bot_log.log')
    file_handler = RotatingFileHandler(log_file_path, maxBytes=10 * 1024 * 1024, backupCount=5)
    console_handler = logging.StreamHandler()

    class CustomFormatter(logging.Formatter):
        FORMATS = {
            logging.DEBUG: Fore.BLUE + "%(asctime)s - DEBUG - %(message)s" + Style.RESET_ALL,
            logging.INFO: Fore.GREEN + "%(asctime)s - INFO - %(message)s" + Style.RESET_ALL,
            logging.WARNING: Fore.YELLOW + "%(asctime)s - WARNING - %(message)s" + Style.RESET_ALL,
            logging.ERROR: Fore.RED + "%(asctime)s - ERROR - %(message)s" + Style.RESET_ALL,
            logging.CRITICAL: Fore.RED + Style.BRIGHT + "%(asctime)s - CRITICAL - %(message)s" + Style.RESET_ALL
        }
        def format(self, record):
            log_fmt = self.FORMATS.get(record.levelno)
            formatter = logging.Formatter(log_fmt)
            return formatter.format(record)

    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    console_handler.setFormatter(CustomFormatter())

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger
