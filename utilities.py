import json
import os
import discord
from datetime import datetime, timedelta
from config import REQUEST_COUNT_FILE, RESET_HOURS
import logging
#from crypt import derive_key, encrypt_data, decrypt_data  # Import cryptography methods if needed
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
    summary: str | None,  # Dynamically use the appropriate type hint
    response_channel_id: int,
    logger: logging.Logger
):
    """
    Route the response to the user and optionally to the response channel.

    Args:
        interaction (discord.Interaction): The interaction object.
        prompt (str): The user's prompt.
        result (str): The full response.
        summary (str | None or Optional[str]): The summarized response, if applicable.
        response_channel_id (int): The ID of the response channel.
        logger (logging.Logger): The logger instance.
    """
    try:
        # If the response is within the summary limit, send it directly to the user
        if not summary:
            logger.info("Response is within the summary limit. Sending directly to the user.")
            chunks = split_message(f"**Prompt:** {prompt}\n**Full Response:** {result}", limit=2000)
            for chunk in chunks:
                await interaction.followup.send(chunk)
            return

        # If a summary exists, send the summary to the user
        await interaction.followup.send(f"✉️: {prompt}\n📫: {summary}")

        # Send the full response to the response channel
        response_channel = interaction.client.get_channel(response_channel_id)
        if response_channel:
            logger.info(f"Response channel found: {response_channel.name} (ID: {response_channel.id})")
            chunks = split_message(f"✉️: {prompt}\n📫: {result}", limit=2000)
            for chunk in chunks:
                await response_channel.send(chunk)
            logger.info("Full response sent to response channel.")
        else:
            logger.error(f"Response channel with ID {response_channel_id} not found.")
    except Exception as e:
        logger.error(f"Error while routing response: {e}", exc_info=True)
        await interaction.followup.send("An error occurred while routing the response.")
