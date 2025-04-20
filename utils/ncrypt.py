import os
import json
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
import base64
import logging  # Added
import hashlib  # Added for safer key handling

logger = logging.getLogger('discord_bot')  # Added logger instance

# Cryptography-related methods are not currently used but may be implemented if needed.

def derive_key(user_id: str, salt: bytes) -> bytes:
    """
    Derive a cryptographic key using the user's ID and a salt.

    Args:
        user_id (str): The user's ID.
        salt (bytes): The salt to use for key derivation.

    Returns:
        bytes: The derived key.
    """
    logger.debug(f"Deriving key for user_id: {user_id} with salt (length: {len(salt)}).")
    # Normalize user_id to ensure consistent key derivation
    user_id_normalized = str(user_id).strip()
    logger.debug(f"Normalized user_id: '{user_id_normalized}'")
    
    # Use a consistent server secret
    secret = os.getenv("SERVER_SECRET", "default_secret").encode()  # Add a server-side secret
    user_key_input = f"{user_id_normalized}:{secret.decode()}".encode()  # Combine user ID with the secret
    
    # Add a hash to make key derivation more stable
    hash_obj = hashlib.sha256(user_key_input)
    hash_digest = hash_obj.digest()
    logger.debug(f"Hash of user key input: {hash_digest[:8]}...")
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    derived_key = kdf.derive(hash_digest)
    key_hash = hashlib.sha256(derived_key).hexdigest()[:8]
    logger.debug(f"Key derived successfully for user_id: {user_id}. Key hash: {key_hash}")
    return derived_key

def encrypt_data(user_id: str, data) -> str:
    """
    Encrypt data using the user's ID as the key.

    Args:
        user_id (str): The user's ID or encryption key.
        data: The data to encrypt (can be a dict, string, or other JSON-serializable type).

    Returns:
        str: The encrypted data as a base64-encoded string.
    """
    logger.debug(f"Encrypting data for user_id: {user_id}. Data type: {type(data)}.")
    try:
        salt = os.urandom(16)  # Generate a unique salt for each user
        logger.debug("Generated salt for encryption.")
        key = derive_key(user_id, salt)
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)  # Generate a random nonce
        logger.debug("Generated nonce for encryption.")
        
        # Handle different data types
        if isinstance(data, str):
            plaintext = data.encode()
        else:
            plaintext = json.dumps(data).encode()
            
        logger.debug(f"Plaintext length: {len(plaintext)} bytes.")
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        logger.debug(f"Ciphertext length: {len(ciphertext)} bytes.")
        result = base64.b64encode(salt + nonce + ciphertext).decode()  # Prepend salt and nonce
        logger.debug(f"Encryption successful for user_id: {user_id}. Result length: {len(result)}.")
        return result
    except Exception as e:
        logger.error(f"Error encrypting data for user_id {user_id}: {e}", exc_info=True)
        raise  # Re-raise the exception after logging

def decrypt_data(user_id: str, encrypted_data: str):
    """
    Decrypt data using the user's ID as the key.

    Args:
        user_id (str): The user's ID or encryption key.
        encrypted_data (str): The encrypted data as a base64-encoded string.

    Returns:
        The decrypted data (either dict or string, depending on the original type).
    """
    logger.debug(f"Decrypting data for user_id: {user_id}. Encrypted data length: {len(encrypted_data)}.")
    try:
        # Start decryption process with verbose logging
        # Normalize user_id to ensure consistent key derivation
        user_id_normalized = str(user_id).strip()
        logger.debug(f"Normalized user_id: '{user_id_normalized}'") 
        
        logger.debug(f"Starting decryption process. Using key: '{user_id[:5]}...'")
        
        encrypted_bytes = base64.b64decode(encrypted_data)
        logger.debug(f"Decoded base64 data length: {len(encrypted_bytes)} bytes.")
        
        if len(encrypted_bytes) < 28:  # 16 bytes salt + 12 bytes nonce
            logger.error(f"Encrypted data too short for user_id {user_id}. Length: {len(encrypted_bytes)}.")
            raise ValueError("Encrypted data is too short to contain salt and nonce.")
        
        salt = encrypted_bytes[:16]  # Extract the salt
        nonce = encrypted_bytes[16:28]  # Extract the nonce
        ciphertext = encrypted_bytes[28:]  # Extract the ciphertext
        logger.debug(f"Extracted salt (len: {len(salt)}), nonce (len: {len(nonce)}), ciphertext (len: {len(ciphertext)}).")
        
        # Log key derivation info
        salt_hash = hashlib.sha256(salt).hexdigest()[:8]
        logger.debug(f"Using salt with hash: {salt_hash}")
        key = derive_key(user_id_normalized, salt)
        
        # Attempt decryption
        aesgcm = AESGCM(key)
        try:
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            logger.debug(f"Decryption successful. Plaintext length: {len(plaintext)} bytes.")
        except Exception as e:
            logger.error(f"AESGCM decryption failed: {e}. This may indicate an invalid key or corrupted data.")
            raise
        
        # Try to parse as JSON, but return as string if it fails
        try:
            decrypted_data = json.loads(plaintext.decode())
            logger.debug(f"Successfully parsed decrypted JSON for user_id: {user_id}.")
            return decrypted_data
        except json.JSONDecodeError:
            # Not valid JSON, probably a string that was encrypted directly
            decrypted_str = plaintext.decode()
            logger.debug(f"Decrypted data is not JSON, returning as string. Length: {len(decrypted_str)}")
            return decrypted_str
            
    except ValueError as e:  # Catch specific errors like invalid tag or short data
        logger.error(f"ValueError during decryption for user_id {user_id}: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Error decrypting data for user_id {user_id}: {e}", exc_info=True)
        raise  # Re-raise the exception after logging
