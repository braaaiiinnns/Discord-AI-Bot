import json
import os
from datetime import datetime, timedelta
from config import REQUEST_COUNT_FILE, RESET_HOURS
import logging

logger = logging.getLogger('discord_bot')

def load_user_request_data():
    if os.path.exists(REQUEST_COUNT_FILE):
        with open(REQUEST_COUNT_FILE, 'r') as file:
            return json.load(file)
    else:
        data = {}
        with open(REQUEST_COUNT_FILE, 'w') as file:
            json.dump(data, file)
        return data

def save_user_request_data(data):
    with open(REQUEST_COUNT_FILE, 'w') as file:
        json.dump(data, file)

def check_and_reset_user_count(user_id, user_data):
    from datetime import datetime, timedelta
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

def split_message(content: str, limit: int = 2000):
    """Split content into chunks of up to 2000 characters."""
    if len(content) <= limit:
        return [content]
    return [content[i : i + limit] for i in range(0, len(content), limit)]