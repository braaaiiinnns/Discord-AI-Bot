
import logging
from logging.handlers import RotatingFileHandler
from colorama import Fore, Style, init

def setup_logging():
    """Setup logging with color-coded console output and file logging."""
    init(autoreset=True)
    logger = logging.getLogger("discord_bot")
    logger.setLevel(logging.DEBUG)

    file_handler = RotatingFileHandler("bot_log.log", maxBytes=1 * 1024 * 1024, backupCount=5)
    console_handler = logging.StreamHandler()

    class CustomFormatter(logging.Formatter):
        FORMATS = {
            logging.DEBUG: Fore.BLUE + "%(asctime)s - DEBUG - %(message)s" + Style.RESET_ALL,
            logging.INFO: Fore.GREEN + "%(asctime)s - INFO - %(message)s" + Style.RESET_ALL,
            logging.WARNING: Fore.YELLOW + "%(asctime)s - WARNING - %(message)s" + Style.RESET_ALL,
            logging.ERROR: Fore.RED + "%(asctime)s - ERROR - %(message)s" + Style.RESET_ALL,
            logging.CRITICAL: Fore.RED + Style.BRIGHT + "%(asctime)s - CRITICAL - %(message)s" + Style.RESET_ALL,
        }

        def format(self, record):
            formatter = logging.Formatter(self.FORMATS.get(record.levelno))
            return formatter.format(record)

    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    console_handler.setFormatter(CustomFormatter())

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
