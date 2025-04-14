import json
import os
import discord
import logging
from datetime import datetime, timedelta
from typing import Optional
from random_ascii_emoji import get_random_emoji
from config import REQUEST_COUNT_FILE, RESET_HOURS

logger = logging.getLogger('discord_bot')

# User request tracking functions
def load_user_request_data():
    """Load user request data from JSON file"""
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
    """Save user request data to JSON file"""
    with open(REQUEST_COUNT_FILE, 'w') as file:
        json.dump(data, file)

def check_and_reset_user_count(user_id, user_data):
    """Check user request count and reset if necessary"""
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
    """Get time until request count reset"""
    last_reset = datetime.fromisoformat(user_data[user_id][reset_type])
    reset_time = last_reset + timedelta(hours=RESET_HOURS)
    time_remaining = reset_time - datetime.now()
    hours, remainder = divmod(time_remaining.seconds, 3600)
    minutes = remainder // 60
    return f"{hours}h{minutes}m"

async def check_request_limit(interaction, user_data, request_limit):
    """Check if user has exceeded their request limit"""
    user_id = str(interaction.user.id)
    if user_data[user_id]['count'] >= request_limit:
        wait_time = time_until_reset(user_data, user_id, 'last_reset')
        await interaction.response.send_message(
            f"Sorry, you've reached your request limit. Please wait {wait_time} before trying again.",
            ephemeral=True
        )
        return False
    # Increment the user's count and persist the change
    user_data[user_id]['count'] += 1
    save_user_request_data(user_data)
    return True

# Response handling functions
def split_message(content: str, limit: int = 2000) -> list:
    """Split content into chunks of up to `limit` characters"""
    if len(content) <= limit:
        return [content]
    return [content[i:i + limit] for i in range(0, len(content), limit)]

async def route_response(
    interaction: discord.Interaction,
    prompt: str,
    result: str,
    summary: Optional[str],
    response_channels: dict,
    logger: logging.Logger
):
    """Route response to user and optionally to a dedicated channel"""
    try:
        # Validate that response_channels is a dictionary
        if not isinstance(response_channels, dict):
            logger.error("Invalid response_channels parameter. Expected a dictionary.")
            await interaction.followup.send("An internal error occurred while routing the response.")
            return

        guild = interaction.guild
        if not guild:
            logger.warning("Interaction does not belong to a guild. Returning full response to the user.")
            chunks = split_message(f"**Prompt:** {prompt}\n**Full Response:** {result}", limit=2000)
            for chunk in chunks:
                await interaction.followup.send(chunk)
            return

        # Resolve the response channel from the cached dictionary
        response_channel = response_channels.get(guild.id)
        if not response_channel:
            logger.error(f"No cached response channel found for guild '{guild.name}'.")
            await interaction.followup.send("The response channel could not be found.")
            return

        # If the response is within the summary limit, send it directly to the user
        if not summary:
            logger.info("Response is within the summary limit. Sending directly to the user.")
            chunks = split_message(f"**Prompt:** {prompt}\n**Full Response:** {result}", limit=2000)
            for chunk in chunks:
                await interaction.followup.send(chunk)
            return  # Skip sending to the response channel

        # If a summary exists, send the summary to the user
        await interaction.followup.send(f"✉️: {prompt}\n📫: {summary}")

        # Append a random emoji to the full response for the response channel
        emoji = get_random_emoji()
        chunks = split_message(f"✉️: {prompt}\n📫: {result}\n\n{emoji}", limit=2000)
        for chunk in chunks:
            await response_channel.send(chunk)
        logger.info("Full response sent to response channel with emoji buffer.")
    except Exception as e:
        logger.error(f"Error while routing response: {e}", exc_info=True)
        await interaction.followup.send("An error occurred while routing the response.")
