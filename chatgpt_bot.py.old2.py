#!/usr/bin/env -S poetry run python

import discord
from openai import OpenAI
import os
from dotenv import load_dotenv
from collections import defaultdict
import json
from datetime import datetime, timedelta

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
RESET_HOURS = 24

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
    if user_id in user_request_data:
        last_reset = datetime.fromisoformat(user_request_data[user_id]['last_reset'])
        if now - last_reset > timedelta(hours=RESET_HOURS):
            # Reset the count and update the reset time
            user_request_data[user_id]['count'] = 0
            user_request_data[user_id]['last_reset'] = now.isoformat()
            save_user_request_data()
    else:
        # Initialize user data if not present
        user_request_data[user_id] = {
            'count': 0,
            'last_reset': now.isoformat()
        }
        save_user_request_data()

def time_until_reset(user_id):
    """Calculate the time remaining until the request count is reset."""
    last_reset = datetime.fromisoformat(user_request_data[user_id]['last_reset'])
    reset_time = last_reset + timedelta(hours=RESET_HOURS)
    time_remaining = reset_time - datetime.now()
    hours, remainder = divmod(time_remaining.seconds, 3600)
    minutes = remainder // 60
    return f"{hours}h{minutes}m"

@discord_client.event
async def on_ready():
    print(f'Logged in as {discord_client.user}')

@discord_client.event
async def on_message(message):
    if message.author == discord_client.user:
        return

    user_id = str(message.author.id)

    # Check and reset the user's request count if necessary
    check_and_reset_user_count(user_id)

    # Check if the user has reached the request limit
    if user_request_data[user_id]['count'] >= REQUEST_LIMIT:
        wait_time = time_until_reset(user_id)
        await message.channel.send(f"Sorry, you've reached the maximum number of requests allowed for today. Please wait {wait_time} before trying again.")
        return

    try:
        # Increment the user's request count
        user_request_data[user_id]['count'] += 1
        save_user_request_data()

        # Non-streaming: Standard Request
        response = client.chat.completions.create(
            model='gpt-4o-mini',  # Use the specified model
            messages=[
                {
                    "role": "user",
                    "content": message.content,
                },
            ],
        )
        # Send the response back to Discord
        await message.channel.send(response.choices[0].message.content.strip())

    except openai.APIError as e:
        print(f"OpenAI API returned an API Error: {e}")
        await message.channel.send("Sorry, there was an issue with the AI service. Please try again later.")

    except openai.APIConnectionError as e:
        print(f"Failed to connect to OpenAI API: {e}")
        await message.channel.send("Sorry, I couldn't connect to the AI service. Please check your connection and try again.")

    except openai.RateLimitError as e:
        print(f"OpenAI API request exceeded rate limit: {e}")
        await message.channel.send("Sorry, I'm receiving too many requests at once. Please try again in a moment.")

    except openai.AuthenticationError as e:
        print(f"OpenAI API authentication error: {e}")
        await message.channel.send("Sorry, it looks like I've run out of credits. Please check back later or contact support.")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        await message.channel.send("Sorry, something went wrong.")

# Run your Discord bot
discord_client.run(os.getenv('DISCORD_BOT_TOKEN'))
