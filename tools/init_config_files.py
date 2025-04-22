#!/usr/bin/env python3
"""
Initialize empty configuration JSON files if they don't exist.
Run this before starting Docker to ensure all required files are present.
"""
import os
import json
import sys
import shutil

# Add the project root to the path so we can import from the app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Required JSON configuration files
CONFIG_FILES = [
    'tasks.json',
    'premium_roles.json',
    'message_listeners.json',
    'previous_role_colors.json',
    'role_color_cycles.json'
]

def init_config_files():
    """Initialize empty configuration files if they don't exist."""
    # Ensure data directory exists
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
    
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        print(f"Created data directory at {data_dir}")
    
    # Create empty config files if they don't exist
    for filename in CONFIG_FILES:
        file_path = os.path.join(data_dir, filename)
        
        if os.path.exists(file_path) and os.path.isdir(file_path):
            # This is a directory instead of a file, so delete it
            shutil.rmtree(file_path)
            print(f"Deleted directory {filename} that was in place of expected JSON file")
        
        if not os.path.exists(file_path):
            # Create an empty JSON file with appropriate structure
            initial_content = {}
            
            # Specific structures for certain files
            if filename == 'tasks.json':
                initial_content = []  # Tasks file should be an empty array
            
            # Write the file
            with open(file_path, 'w') as f:
                json.dump(initial_content, f, indent=2)
            
            print(f"Created empty configuration file: {file_path}")
        else:
            print(f"Configuration file already exists: {file_path}")

if __name__ == "__main__":
    print("Initializing configuration files...")
    init_config_files()
    print("Configuration initialization complete.")