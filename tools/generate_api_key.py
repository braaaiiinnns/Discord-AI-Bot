#!/usr/bin/env python3
"""
Generate a secure API key for the Discord bot's API server.
This script will generate a random secure key and add or update it in your .env file.
"""

import os
import secrets
import string
from pathlib import Path
from dotenv import load_dotenv, set_key
import sys

# Add the project root to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the API key manager
from utils.api_key_manager import api_key_manager

def update_env_file(key_name, key_value):
    """Update the .env file with the new API key."""
    # Find the .env file (look in current dir and parent dir)
    env_path = Path('.env')
    if not env_path.is_file():
        # Try the parent directory
        env_path = Path('..') / '.env'
    
    if not env_path.is_file():
        # Create a new .env file
        env_path = Path('.env')
        env_path.touch()
    
    # Update the .env file
    set_key(str(env_path.absolute()), key_name, key_value)
    
    return env_path

def main():
    # Generate a secure API key using our new API key manager
    api_key = api_key_manager.generate_key()
    
    # Update the .env file
    env_path = update_env_file("API_SECRET_KEY", api_key)
    
    print(f"\n✅ API key generated successfully!")
    print(f"The key has been saved to {env_path.absolute()}\n")
    print("To use this key with API requests, include one of these headers:")
    print(f"  Authorization: Bearer {api_key}")
    print("  or")
    print(f"  X-API-Key: {api_key}\n")
    print("Remember to restart your bot for the new API key to take effect.\n")
    
    # Extract and display key information
    key_info = api_key_manager.extract_data_from_key(api_key)
    if key_info.get('type') == 'structured':
        print(f"Key ID: {key_info.get('key_id')}")
        print(f"Created: {key_info.get('created_at')}")
    
    # Offer to copy the key to clipboard if pyperclip is available
    try:
        import pyperclip
        pyperclip.copy(api_key)
        print("✓ API key has been copied to clipboard.\n")
    except (ImportError, ModuleNotFoundError):
        pass

if __name__ == "__main__":
    main()