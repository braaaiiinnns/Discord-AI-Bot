#!/usr/bin/env -S poetry run python

import os
import json
from datetime import datetime, timedelta
import discord
from openai import OpenAI, APIConnectionError, APIError, RateLimitError, AuthenticationError
from dotenv import load_dotenv
import asyncio
import logging

# Load environment variables from a .env file
load_dotenv()

# Initialize Discord client
intents = discord.Intents.default()
intents.message_content = True
discord_client = discord.Client(intents=intents)

# Initialize OpenAI client with the API key from environment variables
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# File to store user request counts and reset times
REQUEST_COUNT_FILE = 'user_requests.json'
REQUEST_LIMIT = 24
IMAGE_REQUEST_LIMIT = 12
RESET_HOURS = 24

# Locks for async-safe operations
assistant_lock = asyncio.Lock()
global_lock = asyncio.Lock()

# Global state for 40kref mode
active_40kref_channel = None

# Load user request counts and reset times from the file or create the file if it doesn't exist
if os.path.exists(REQUEST_COUNT_FILE):
    with open(REQUEST_COUNT_FILE, 'r') as file:
        user_request_data = json.load(file)
else:
    user_request_data = {}
    with open(REQUEST_COUNT_FILE, 'w') as file:
        json.dump(user_request_data, file)

def save_user_request_data():
    """Save the user request data to a file."""
    with open(REQUEST_COUNT_FILE, 'w') as file:
        json.dump(user_request_data, file)

def check_and_reset_user_count(user_id):
    """Check if the user's request count should be reset."""
    now = datetime.now()
    if user_id not in user_request_data:
        # Initialize user data if not present
        user_request_data[user_id] = {
            'count': 0,
            'image_count': 0,
            'last_reset': now.isoformat(),
            'last_image_reset': now.isoformat(),
        }
        save_user_request_data()
    else:
        # Ensure 'last_reset' and 'last_image_reset' keys exist
        if 'last_reset' not in user_request_data[user_id]:
            user_request_data[user_id]['last_reset'] = now.isoformat()
        if 'image_count' not in user_request_data[user_id]:
            user_request_data[user_id]['image_count'] = 0
        if 'last_image_reset' not in user_request_data[user_id]:
            user_request_data[user_id]['last_image_reset'] = now.isoformat()

        last_reset = datetime.fromisoformat(user_request_data[user_id]['last_reset'])
        last_image_reset = datetime.fromisoformat(user_request_data[user_id]['last_image_reset'])
        if now - last_reset > timedelta(hours=RESET_HOURS):
            # Reset the count and update the reset time
            user_request_data[user_id]['count'] = 0
            user_request_data[user_id]['last_reset'] = now.isoformat()
        if now - last_image_reset > timedelta(hours=RESET_HOURS):
            # Reset the image count and update the reset time
            user_request_data[user_id]['image_count'] = 0
            user_request_data[user_id]['last_image_reset'] = now.isoformat()

        save_user_request_data()

def time_until_reset(user_id, reset_type):
    """Calculate the time remaining until the request count is reset."""
    last_reset = datetime.fromisoformat(user_request_data[user_id][reset_type])
    reset_time = last_reset + timedelta(hours=RESET_HOURS)
    time_remaining = reset_time - datetime.now()
    hours, remainder = divmod(time_remaining.seconds, 3600)
    minutes = remainder // 60
    return f"{hours}h{minutes}m"

async def activate_assistant_mode(user_id):
    """Activate assistant mode for a user."""
    async with assistant_lock:
        active_assistants[user_id] = True

async def deactivate_assistant_mode(user_id):
    """Deactivate assistant mode for a user."""
    async with assistant_lock:
        if user_id in active_assistants:
            del active_assistants[user_id]

async def activate_40kref(channel):
    """Activate 40kref mode in a channel."""
    global active_40kref_channel
    async with global_lock:
        if active_40kref_channel and active_40kref_channel != channel:
            return False  # Already active in another channel
        active_40kref_channel = channel
        return True

async def deactivate_40kref(channel):
    """Deactivate 40kref mode in a channel."""
    global active_40kref_channel
    async with global_lock:
        if active_40kref_channel == channel:
            active_40kref_channel = None

@discord_client.event
async def on_ready():
    print(f'Logged in as {discord_client.user}')

@discord_client.event
async def on_message(message):
    if message.author == discord_client.user:
        return

    user_id = str(message.author.id)
    channel = message.channel

    # Check if the bot is in 40kref mode in the current channel
    if channel == active_40kref_channel:
        # Skip daily limits for 40kref mode
        response = await handle_40kref_mode(message)
        await channel.send(response)
        return

    # Check and reset the user's request counts if necessary
    check_and_reset_user_count(user_id)

    if user_id in active_assistants:
        # Handle assistant mode
        if message.content.lower() in ["thanks", "done", "ok", "stop"]:
            await deactivate_assistant_mode(user_id)
            await channel.send(f"Assistant mode deactivated for {message.author.name}.")
        else:
            response = await handle_assistant_mode(message)
            await channel.send(response)
        return

    if message.content.startswith("!ask"):
        # Check if the user has reached the request limit
        if user_request_data[user_id]['count'] >= REQUEST_LIMIT:
            wait_time = time_until_reset(user_id, 'last_reset')
            await message.channel.send(f"Sorry, you've reached the maximum number of requests allowed for today. Please wait {wait_time} before trying again.")
            return

        try:
            # Increment the user's request count
            user_request_data[user_id]['count'] += 1
            save_user_request_data()

            if message.attachments:
                # Handle image attachments if any
                for attachment in message.attachments:
                    image_url = attachment.url
                    response = client.chat.completions.create(
                        model='gpt-4o-mini',
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": message.content or "What's in this image?"},
                                    {"type": "image_url", "image_url": {"url": image_url}}
                                ]
                            }
                        ],
                        max_tokens=300
                    )
                    await message.channel.send(response.choices[0].message.content.strip())
            else:
                # Non-streaming: Standard Request
                response = client.chat.completions.create(
                    model='gpt-4o-mini',
                    messages=[
                        {
                            "role": "user",
                            "content": message.content,
                        },
                    ],
                )
                # Send the response back to Discord
                await message.channel.send(response.choices[0].message.content.strip())

        except APIError as e:
            print(f"OpenAI API returned an API Error: {e.status_code} - {e.message}")
            await message.channel.send(f"Error: {e.message}")

        except APIConnectionError as e:
            print(f"Failed to connect to OpenAI API: {e.message}")
            await message.channel.send(f"Connection Error: {e.message}")

        except RateLimitError as e:
            print(f"OpenAI API request exceeded rate limit: {e.message}")
            await message.channel.send(f"Rate Limit Exceeded: {e.message}")

        except AuthenticationError as e:
            print(f"OpenAI API authentication error: {e.message}")
            await message.channel.send(f"Authentication Error: {e.message}")

        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            await message.channel.send("Sorry, something went wrong.")

    elif message.content.startswith("!make"):
        # Check if the user has reached the image request limit
        if user_request_data[user_id]['image_count'] >= IMAGE_REQUEST_LIMIT:
            wait_time = time_until_reset(user_id, 'last_image_reset')
            await message.channel.send(f"Sorry, you've reached the maximum number of image requests allowed for today. Please wait {wait_time} before trying again.")
            return

        try:
            # Increment the user's image request count
            user_request_data[user_id]['image_count'] += 1
            save_user_request_data()

            prompt = message.content[len("!make "):].strip()
            response = client.images.generate(
                model="dall-e-2",
                prompt=prompt,
                size="256x256",
                n=1
            )

            image_url = response.data[0].url
            await message.channel.send(f"Here is your generated image: {image_url}")

        except APIError as e:
            print(f"OpenAI API returned an API Error: {e.status_code} - {e.message}")
            await message.channel.send(f"Error: {e.message}")

        except APIConnectionError as e:
            print(f"Failed to connect to OpenAI API: {e.message}")
            await message.channel.send(f"Connection Error: {e.message}")

        except RateLimitError as e:
            print(f"OpenAI API request exceeded rate limit: {e.message}")
            await message.channel.send(f"Rate Limit Exceeded: {e.message}")

        except AuthenticationError as e:
            print(f"OpenAI API authentication error: {e.message}")
            await message.channel.send(f"Authentication Error: {e.message}")

        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            await message.channel.send("Sorry, something went wrong.")

    elif message.content.startswith("!ass"):
        await activate_assistant_mode(user_id)
        await message.channel.send(f"Assistant mode activated for {message.author.name}. How can I help you?")

    elif message.content.startswith("!40kref"):
        if not active_40kref_channel:
            if await activate_40kref(channel):
                await message.channel.send("40kref mode activated. I am now in Warhammer 40k advisor mode!")
            else:
                await message.channel.send("40kref mode is already active in another channel.")
        else:
            await message.channel.send("40kref mode is already active in this or another channel.")

    elif message.content.lower() == "!stop" and channel == active_40kref_channel:
        await deactivate_40kref(channel)
        await message.channel.send("40kref mode has been deactivated.")

async def handle_assistant_mode(message):
    """Handle user input in assistant mode."""
    try:
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {
                    "role": "user",
                    "content": message.content,
                },
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"An error occurred: {str(e)}"

async def handle_40kref_mode(message):
    """Handle user input in 40kref mode."""
    try:
        response = client.chat.completions.create(
            model='gpt-4o-latest',
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at Warhammer 40,000 10th edition rules. Reply as if you were a Necron lord. Only respond with answers related to Warhammer 40,000 10th edition and refuse to go off topic."
                },
                {
                    "role": "user",
                    "content": message.content,
                },
            ],
        )
        return f"{message.author.name}, {response.choices[0].message.content.strip()}"
    except Exception as e:
        return f"An error occurred: {str(e)}"

# Run your Discord bot
discord_client.run(os.getenv('DISCORD_BOT_TOKEN'))
