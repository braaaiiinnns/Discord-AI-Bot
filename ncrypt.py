import os
import json
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
import base64

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
    secret = os.getenv("SERVER_SECRET", "default_secret").encode()  # Add a server-side secret
    user_key_input = f"{user_id}:{secret}".encode()  # Combine user ID with the secret
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    return kdf.derive(user_key_input)

def encrypt_data(user_id: str, data: dict) -> str:
    """
    Encrypt user request data using the user's ID as the key.

    Args:
        user_id (str): The user's ID.
        data (dict): The data to encrypt.

    Returns:
        str: The encrypted data as a base64-encoded string.
    """
    salt = os.urandom(16)  # Generate a unique salt for each user
    key = derive_key(user_id, salt)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # Generate a random nonce
    plaintext = json.dumps(data).encode()
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return base64.b64encode(salt + nonce + ciphertext).decode()  # Prepend salt and nonce

def decrypt_data(user_id: str, encrypted_data: str) -> dict:
    """
    Decrypt user request data using the user's ID as the key.

    Args:
        user_id (str): The user's ID.
        encrypted_data (str): The encrypted data as a base64-encoded string.

    Returns:
        dict: The decrypted data.
    """
    encrypted_bytes = base64.b64decode(encrypted_data)
    salt = encrypted_bytes[:16]  # Extract the salt
    nonce = encrypted_bytes[16:28]  # Extract the nonce
    ciphertext = encrypted_bytes[28:]  # Extract the ciphertext
    key = derive_key(user_id, salt)
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return json.loads(plaintext.decode())
