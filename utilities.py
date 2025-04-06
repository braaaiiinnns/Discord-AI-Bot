import json
import os
import discord
from datetime import datetime, timedelta
from config import REQUEST_COUNT_FILE, RESET_HOURS
import logging
# from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
# from cryptography.hazmat.primitives import hashes
# from cryptography.hazmat.primitives.ciphers.aead import AESGCM
# from cryptography.hazmat.backends import default_backend
# import base64
from typing import Optional  # Import Optional for older Python versions

logger = logging.getLogger('discord_bot')  # Ensure consistent logger name

# Check Python version to determine type hinting style
try:
    summary_type_hint = str | None  # Python 3.10+ syntax
except TypeError:
    from typing import Optional
    summary_type_hint = Optional[str]  # Fallback for older Python versions

def load_user_request_data():
    if os.path.exists(REQUEST_COUNT_FILE):
        try:
            with open(REQUEST_COUNT_FILE, 'r') as file:
                return json.load(file)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON: {e}")
            return {}
    else:
        data = {}
        with open(REQUEST_COUNT_FILE, 'w') as file:
            json.dump(data, file)
        return data

def save_user_request_data(data):
    with open(REQUEST_COUNT_FILE, 'w') as file:
        json.dump(data, file)

def check_and_reset_user_count(user_id, user_data):
    now = datetime.now()
    if user_id not in user_data:
        user_data[user_id] = {
            'count': 0,
            'image_count': 0,
            'last_reset': now.isoformat(),
            'last_image_reset': now.isoformat(),
        }
    else:
        if 'last_reset' not in user_data[user_id]:
            user_data[user_id]['last_reset'] = now.isoformat()
        if 'image_count' not in user_data[user_id]:
            user_data[user_id]['image_count'] = 0
        if 'last_image_reset' not in user_data[user_id]:
            user_data[user_id]['last_image_reset'] = now.isoformat()
        
        last_reset = datetime.fromisoformat(user_data[user_id]['last_reset'])
        last_image_reset = datetime.fromisoformat(user_data[user_id]['last_image_reset'])
        if now - last_reset > timedelta(hours=RESET_HOURS):
            user_data[user_id]['count'] = 0
            user_data[user_id]['last_reset'] = now.isoformat()
        if now - last_image_reset > timedelta(hours=RESET_HOURS):
            user_data[user_id]['image_count'] = 0
            user_data[user_id]['last_image_reset'] = now.isoformat()
    return user_data

def time_until_reset(user_data, user_id, reset_type):
    last_reset = datetime.fromisoformat(user_data[user_id][reset_type])
    reset_time = last_reset + timedelta(hours=RESET_HOURS)
    time_remaining = reset_time - datetime.now()
    hours, remainder = divmod(time_remaining.seconds, 3600)
    minutes = remainder // 60
    return f"{hours}h{minutes}m"

async def check_request_limit(message, user_data, request_limit):
    """
    Checks if the user has exceeded their request limit.
    If exceeded, sends a message with the wait time.
    Otherwise, increments the count and returns True.
    """
    user_id = str(message.author.id)
    if user_data[user_id]['count'] >= request_limit:
        wait_time = time_until_reset(user_data, user_id, 'last_reset')
        await message.channel.send(
            f"Sorry, you've reached your request limit. Please wait {wait_time} before trying again."
        )
        return False
    # Increment the user's count and persist the change
    user_data[user_id]['count'] += 1
    save_user_request_data(user_data)
    return True

def compose_text_response(prompt: str, answer: str) -> str:
    """Compose a text response that shows both the prompt and reply."""
    return f"**Prompt:** {prompt}\n**Answer:** {answer}"

def split_message(content: str, limit: int = 2000) -> list[str]:
    """
    Split content into chunks of up to `limit` characters.

    Args:
        content (str): The content to split.
        limit (int): The maximum length of each chunk.

    Returns:
        list[str]: A list of content chunks.
    """
    if len(content) <= limit:
        return [content]
    return [content[i:i + limit] for i in range(0, len(content), limit)]

async def route_response(
    interaction: discord.Interaction,
    prompt: str,
    result: str,
    summary: summary_type_hint,  # Dynamically use the appropriate type hint
    summary_channel_id: int,
    logger: logging.Logger
):
    """
    Route the response to the user and optionally to the summary channel.

    Args:
        interaction (discord.Interaction): The interaction object.
        prompt (str): The user's prompt.
        result (str): The full response.
        summary (str | None or Optional[str]): The summarized response, if applicable.
        summary_channel_id (int): The ID of the summary channel.
        logger (logging.Logger): The logger instance.
    """
    if summary:
        await interaction.followup.send(f"**Prompt:** {prompt}\n**Summary:** {summary}")

    summary_channel = interaction.client.get_channel(summary_channel_id)
    if summary_channel:
        logger.info(f"Summary channel found: {summary_channel.name} (ID: {summary_channel.id})")
        chunks = split_message(f"**Prompt:** {prompt}\n**Full Response:** {result}", limit=2000)
        for chunk in chunks:
            await summary_channel.send(chunk)
        logger.info("Full response sent to summary channel.")
    else:
        logger.error(f"Summary channel with ID {summary_channel_id} not found.")
        await interaction.followup.send("The summary channel is not available.")

#-------------------------------------------------------------------------------------------

# Cryptography-related methods are not currently used. Commented out for now.
# def derive_key(user_id: str, salt: bytes) -> bytes:
#     """
#     Derive a cryptographic key using the user's ID and a salt.
#
#     Args:
#         user_id (str): The user's ID.
#         salt (bytes): The salt to use for key derivation.
#
#     Returns:
#         bytes: The derived key.
#     """
#     secret = os.getenv("SERVER_SECRET", "default_secret").encode()  # Add a server-side secret
#     user_key_input = f"{user_id}:{secret}".encode()  # Combine user ID with the secret
#     kdf = PBKDF2HMAC(
#         algorithm=hashes.SHA256(),
#         length=32,
#         salt=salt,
#         iterations=100000,
#         backend=default_backend()
#     )
#     return kdf.derive(user_key_input)

# def encrypt_data(user_id: str, data: dict) -> str:
#     """
#     Encrypt user request data using the user's ID as the key.
#
#     Args:
#         user_id (str): The user's ID.
#         data (dict): The data to encrypt.
#
#     Returns:
#         str: The encrypted data as a base64-encoded string.
#     """
#     salt = os.urandom(16)  # Generate a unique salt for each user
#     key = derive_key(user_id, salt)
#     aesgcm = AESGCM(key)
#     nonce = os.urandom(12)  # Generate a random nonce
#     plaintext = json.dumps(data).encode()
#     ciphertext = aesgcm.encrypt(nonce, plaintext, None)
#     return base64.b64encode(salt + nonce + ciphertext).decode()  # Prepend salt and nonce

# def decrypt_data(user_id: str, encrypted_data: str) -> dict:
#     """
#     Decrypt user request data using the user's ID as the key.
#
#     Args:
#         user_id (str): The user's ID.
#         encrypted_data (str): The encrypted data as a base64-encoded string.
#
#     Returns:
#         dict: The decrypted data.
#     """
#     encrypted_bytes = base64.b64decode(encrypted_data)
#     salt = encrypted_bytes[:16]  # Extract the salt
#     nonce = encrypted_bytes[16:28]  # Extract the nonce
#     ciphertext = encrypted_bytes[28:]  # Extract the ciphertext
#     key = derive_key(user_id, salt)
#     aesgcm = AESGCM(key)
#     plaintext = aesgcm.decrypt(nonce, ciphertext, None)
#     return json.loads(plaintext.decode())
