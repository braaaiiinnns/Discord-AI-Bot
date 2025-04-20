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

def generate_secure_key(length=48):
    """Generate a cryptographically secure random string of specified length."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def update_env_file(key_name, key_value):
    """Update the .env file with the new API key."""
    dotenv_path = Path(".env")
    
    # Create .env file if it doesn't exist
    if not dotenv_path.exists():
        dotenv_path.touch()
    
    # Load current env variables
    load_dotenv(dotenv_path)
    
    # Set the new API key
    set_key(dotenv_path, key_name, key_value)
    
    return dotenv_path

def main():
    # Generate a secure API key
    api_key = generate_secure_key()
    
    # Update the .env file
    env_path = update_env_file("API_SECRET_KEY", api_key)
    
    print(f"\n✅ API key generated successfully!")
    print(f"The key has been saved to {env_path.absolute()}\n")
    print("To use this key with API requests, include one of these headers:")
    print(f"  Authorization: Bearer {api_key}")
    print("  or")
    print(f"  X-API-Key: {api_key}\n")
    print("Remember to restart your bot for the new API key to take effect.\n")
    
    # Offer to copy the key to clipboard if pyperclip is available
    try:
        import pyperclip
        pyperclip.copy(api_key)
        print("✓ API key has been copied to clipboard.\n")
    except (ImportError, ModuleNotFoundError):
        pass

if __name__ == "__main__":
    main()