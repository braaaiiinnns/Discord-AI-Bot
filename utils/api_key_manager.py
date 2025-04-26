"""
API Key Manager Module

This module handles API key generation, validation, and management for the Discord bot.
It provides a more robust and centralized approach to API key handling.
"""

import os
import secrets
import logging
import hashlib
import hmac
import time
import base64
import json
from typing import Dict, Optional, Tuple, Union, Any
from datetime import datetime, timedelta

# Set up logger
logger = logging.getLogger('discord_bot.api_key_manager')

class ApiKeyManager:
    """
    Manages API keys for the Discord bot, handling validation, generation, and verification.
    
    This class provides a central point for all API key related operations and enforces
    consistent security practices across the application.
    """
    
    def __init__(self, env_var_name: str = 'API_SECRET_KEY', key_length: int = 48):
        """
        Initialize the API key manager.
        
        Args:
            env_var_name: The name of the environment variable holding the master API key
            key_length: The length of generated API keys in bytes
        """
        self.env_var_name = env_var_name
        self.key_length = key_length
        self.master_key = self._load_master_key()
        self.key_cache = {}  # Simple in-memory cache for validated keys
        self.cache_ttl = 300  # Cache TTL in seconds (5 minutes)
    
    def _load_master_key(self) -> str:
        """
        Load the master API key from environment variables.
        
        Returns:
            The master API key
        """
        master_key = os.environ.get(self.env_var_name)
        if not master_key:
            # Generate a new key if not found (for development only)
            if os.environ.get('FLASK_ENV') != 'production':
                master_key = self.generate_key()
                logger.warning(f"No {self.env_var_name} found in environment. Generated temporary key: {master_key[:5]}...")
            else:
                logger.critical(f"No {self.env_var_name} found in production environment!")
                raise ValueError(f"Missing required environment variable: {self.env_var_name}")
        return master_key
    
    def generate_key(self) -> str:
        """
        Generate a new secure API key.
        
        Returns:
            A new secure API key
        """
        # Generate a random key
        random_key = secrets.token_urlsafe(self.key_length)
        
        # Create a timestamp component for uniqueness
        timestamp = int(time.time())
        
        # Create a signature using the master key
        if self.master_key:
            signature = self._create_signature(random_key, timestamp)
            key_parts = [random_key, str(timestamp), signature]
            api_key = '.'.join(key_parts)
        else:
            # Fallback if no master key is available
            api_key = random_key
        
        return api_key
    
    def validate_key(self, api_key: str) -> bool:
        """
        Validate an API key.
        
        Args:
            api_key: The API key to validate
            
        Returns:
            True if valid, False otherwise
        """
        # Reject empty, None, or undefined keys immediately
        if not api_key or api_key == "undefined" or api_key == "null":
            logger.warning("Empty or invalid API key provided")
            return False
            
        # Check cache first for performance
        if api_key in self.key_cache:
            cache_entry = self.key_cache[api_key]
            if time.time() < cache_entry['expires_at']:
                logger.debug(f"API key validation cache hit: {api_key[:5]}...")
                return cache_entry['valid']
            else:
                # Remove expired entry
                del self.key_cache[api_key]
        
        try:
            # For simple keys without signature (legacy or temporary keys)
            if '.' not in api_key:
                # For the master key check
                if self.master_key and hmac.compare_digest(api_key, self.master_key):
                    self._update_cache(api_key, True)
                    return True
                    
                # For backward compatibility, check if we've stored this key in the database
                # Database check will be handled separately by the user_manager
                
                # Don't cache simple keys, let the database handle validation
                return False
            
            # For new format keys with signature
            parts = api_key.split('.')
            if len(parts) != 3:
                logger.warning(f"Invalid API key format: {api_key[:5]}...")
                self._update_cache(api_key, False)
                return False
            
            random_key, timestamp_str, sig = parts
            
            try:
                timestamp = int(timestamp_str)
                
                # Verify signature
                expected_sig = self._create_signature(random_key, timestamp)
                if hmac.compare_digest(sig, expected_sig):
                    self._update_cache(api_key, True)
                    return True
                else:
                    logger.warning(f"Invalid API key signature: {api_key[:5]}...")
                    self._update_cache(api_key, False)
                    return False
            except ValueError:
                logger.warning(f"Invalid timestamp in API key: {api_key[:5]}...")
                self._update_cache(api_key, False)
                return False
                
        except Exception as e:
            logger.error(f"Error validating API key: {e}", exc_info=True)
            return False
    
    def _create_signature(self, key_data: str, timestamp: int) -> str:
        """
        Create a signature for an API key.
        
        Args:
            key_data: The random part of the API key
            timestamp: The timestamp when the key was generated
            
        Returns:
            A signature for the API key
        """
        # Create a message combining the random key and timestamp
        message = f"{key_data}:{timestamp}"
        
        # Create a signature using HMAC
        signature = hmac.new(
            key=self.master_key.encode('utf-8'),
            msg=message.encode('utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()
        
        return signature[:16]  # Return first 16 chars for brevity
    
    def _update_cache(self, api_key: str, valid: bool) -> None:
        """
        Update the validation cache.
        
        Args:
            api_key: The API key
            valid: Whether the key is valid
        """
        self.key_cache[api_key] = {
            'valid': valid,
            'expires_at': time.time() + self.cache_ttl
        }
    
    def extract_data_from_key(self, api_key: str) -> Dict[str, Any]:
        """
        Extract data embedded in the API key.
        
        Args:
            api_key: The API key
            
        Returns:
            A dictionary containing data extracted from the key
        """
        if '.' not in api_key:
            return {'type': 'simple'}
            
        parts = api_key.split('.')
        if len(parts) != 3:
            return {'type': 'unknown', 'valid': False}
            
        random_key, timestamp_str, sig = parts
        
        try:
            timestamp = int(timestamp_str)
            created_date = datetime.fromtimestamp(timestamp)
            
            return {
                'type': 'structured',
                'created_at': created_date.isoformat(),
                'key_id': random_key[:8],  # First 8 chars as a key identifier
                'valid': self.validate_key(api_key)
            }
        except Exception:
            return {'type': 'invalid', 'valid': False}

# Global instance for easy access
api_key_manager = ApiKeyManager()