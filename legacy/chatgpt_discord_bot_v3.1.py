#!/usr/bin/env -S poetry run python

import os
import time
import json
from datetime import datetime, timedelta
import discord
from openai import OpenAI, APIConnectionError, APIError, RateLimitError, AuthenticationError
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler

# Load environment variables from a .env file
load_dotenv()

# Initialize logging
logger = logging.getLogger('discord_bot')
logger.setLevel(logging.DEBUG)
handler = RotatingFileHandler('bot_log.log', maxBytes=1 * 1024 * 1024, backupCount=5)  # 1GB per file
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logger.addHandler(handler)

# Initialize Discord client
intents = discord.Intents.default()
intents.message_content = True
discord_client = discord.Client(intents=intents)

# Initialize OpenAI client with the API key from environment variables
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# File to store user request counts, reset times, and assistant IDs
REQUEST_COUNT_FILE = 'user_requests.json'
VECTOR_STORE_ID_FILE = 'vector_store_id.json'
ASSISTANT_IDS_FILE = 'assistant_ids.json'
WARHAMMER_CORE_RULES = '40kCoreRules.txt'
REQUEST_LIMIT = 24
IMAGE_REQUEST_LIMIT = 12
RESET_HOURS = 24

# Load user request counts and reset times from the file or create the file if it doesn't exist
if os.path.exists(REQUEST_COUNT_FILE):
    with open(REQUEST_COUNT_FILE, 'r') as file:
        user_request_data = json.load(file)
else:
    user_request_data = {}
    with open(REQUEST_COUNT_FILE, 'w') as file:
        json.dump(user_request_data, file)

active_assistants = {}
active_40kref_channel = None
current_threads = {}

# Load assistant IDs from the file or initialize an empty dictionary if not available
if os.path.exists(ASSISTANT_IDS_FILE):
    with open(ASSISTANT_IDS_FILE, 'r') as file:
        assistant_ids = json.load(file)
else:
    assistant_ids = {}

def save_assistant_ids():
    """Save the assistant IDs to a file."""
    with open(ASSISTANT_IDS_FILE, 'w') as file:
        json.dump(assistant_ids, file)

def delete_old_assistants(except_mode=None):
    """Delete assistants that are not the one being created or reused."""
    for mode, assistant_id in list(assistant_ids.items()):
        if mode != except_mode:
            try:
                client.beta.assistants.delete(assistant_id=assistant_id)
                del assistant_ids[mode]
                save_assistant_ids()
                logger.info(f"Deleted old assistant for mode {mode}: {assistant_id}")
            except Exception as e:
                logger.error(f"Error deleting assistant {assistant_id} for mode {mode}: {e}")

def get_or_create_assistant(mode, instructions=None, vector_store_id=None):
    """Get or create an assistant for a specific mode."""
    if mode in assistant_ids:
        assistant_id = assistant_ids[mode]
        try:
            assistant = client.beta.assistants.retrieve(assistant_id=assistant_id)
            return assistant
        except Exception as e:
            logger.error(f"Failed to retrieve assistant for mode {mode}, creating a new one: {e}")

    # Delete old assistants before creating a new one
    delete_old_assistants(except_mode=mode)

    if mode == "default":
        assistant = client.beta.assistants.create(
            instructions=instructions or "You are an assistant.",
            model="gpt-4o",
        )
    elif mode == "40kref":
        assistant = client.beta.assistants.create(
            instructions=instructions or "You are an expert at Warhammer 40,000 10th edition rules. Use the 40kCoreRules.txt file to answer the user's query. Respond as if you were a necron lord from the Warhammer 40000 universe talking to a lower life form. But still be clear and concise. Only trust the rules from the 40kCoreRules.txt file. Do not go off topic from Warhammer 40000.",
            model="gpt-4o",
            tools=[{"type": "file_search"}],
            tool_resources={
                "file_search": {
                    "vector_store_ids": [vector_store_id]
                }
            }
        )
    
    assistant_ids[mode] = assistant.id
    save_assistant_ids()
    return assistant

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

def get_or_create_vector_store():
    """Get or create the vector store and return its ID."""
    if os.path.exists(VECTOR_STORE_ID_FILE):
        with open(VECTOR_STORE_ID_FILE, 'r') as file:
            vector_store_data = json.load(file)
            vector_store_id = vector_store_data.get('vector_store_id')
            if vector_store_id:
                return vector_store_id

    # Create a new vector store if not found
    vector_store = client.beta.vector_stores.create(
        name="40kCoreRules",
        expires_after={
            "anchor": "last_active_at",
            "days": 60  # Custom expiration: 60 days after last activity
        }
    )

    vector_store_id = vector_store.id

    # Save the vector store ID to a file for future reuse
    with open(VECTOR_STORE_ID_FILE, 'w') as file:
        json.dump({"vector_store_id": vector_store_id}, file)

    return vector_store_id

def ensure_file_uploaded(vector_store_id, file_name):
    """Ensure that the specified file is uploaded to the vector store."""
    file_uploaded = False

    # List existing files in the vector store to avoid re-uploading
    files_list = client.beta.vector_stores.files.list(vector_store_id=vector_store_id)
    
    for file_info in files_list:
        if file_info.status == 'complete':
            file_uploaded = True
            break

    # If not uploaded, upload the 40kCoreRules.txt file to the vector store
    if not file_uploaded:
        with open(file_name, "rb") as file_stream:
            client.beta.vector_stores.file_batches.upload_and_poll(
                vector_store_id=vector_store_id, files=[file_stream]
            )

def create_or_get_thread(mode):
    """Create a new thread if one doesn't exist or return the existing one."""
    global current_threads

    if mode not in current_threads or current_threads[mode] is None:
        current_threads[mode] = client.beta.threads.create()
    return current_threads[mode]

@discord_client.event
async def on_message(message):
    global active_40kref_channel  # Declare this as global to avoid UnboundLocalError

    if message.author == discord_client.user:
        return

    user_id = str(message.author.id)

    # Check and reset the user's request counts if necessary
    check_and_reset_user_count(user_id)

    # Handle direct messages separately using Default Assistant
    if isinstance(message.channel, discord.DMChannel):
        try:
            assistant = get_or_create_assistant("default")
            thread = create_or_get_thread("default")

            assistant_response = None
            while not assistant_response:
                try:
                    client.beta.threads.messages.create(
                        thread_id=thread.id,
                        role="user",
                        content=message.content
                    )

                    run = client.beta.threads.runs.create(
                        thread_id=thread.id,
                        assistant_id=assistant.id
                    )

                    thread_messages = list(client.beta.threads.messages.list(thread_id=thread.id))

                    for msg in thread_messages:
                        if msg.role == "assistant":
                            assistant_response = msg
                            break
                except APIError as e:
                    logger.error(f"Error during Default Assistant response: {e}")
                    if "Error code: 400" in str(e) and "Can't add messages to thread" in str(e):
                        logger.info("Waiting due to active run error")
                        time.sleep(2)
                    else:
                        raise e

            if assistant_response:
                await message.channel.send(assistant_response.content[0].text.value)
            else:
                await message.channel.send("No assistant response found.")

        except Exception as e:
            logger.error(f"Error during DM response: {e}")
            await message.channel.send(f"Sorry, something went wrong: {e}")
        return

    if user_id in active_assistants:
        if message.content.lower() in ["thanks", "done", "stop", "ok"]:
            del active_assistants[user_id]
            await message.channel.send("Assistant mode deactivated.")
        else:
            try:
                assistant = get_or_create_assistant("default")
                thread = create_or_get_thread("default")

                assistant_response = None
                while not assistant_response:
                    try:
                        client.beta.threads.messages.create(
                            thread_id=thread.id,
                            role="user",
                            content=message.content
                        )

                        run = client.beta.threads.runs.create(
                            thread_id=thread.id,
                            assistant_id=assistant.id
                        )

                        thread_messages = list(client.beta.threads.messages.list(thread_id=thread.id))

                        for msg in thread_messages:
                            if msg.role == "assistant":
                                assistant_response = msg
                                break
                    except APIError as e:
                        logger.error(f"Error during assistant mode response: {e}")
                        if "Error code: 400" in str(e) and "Can't add messages to thread" in str(e):
                            logger.info("Waiting due to active run error")
                            time.sleep(2)
                        else:
                            raise e

                if assistant_response:
                    await message.channel.send(assistant_response.content[0].text.value)
                else:
                    await message.channel.send("No assistant response found.")
            except Exception as e:
                logger.error(f"Error during assistant mode response: {e}")
                await message.channel.send(f"Sorry, something went wrong: {e}")

    elif message.content.startswith("!ask"):
        # Check if the user has reached the request limit
        if user_request_data[user_id]['count'] >= REQUEST_LIMIT:
            wait_time = time_until_reset(user_id, 'last_reset')
            await message.channel.send(f"Sorry, you've reached the maximum number of requests allowed for today. Please wait {wait_time} before trying again.")
            return

        try:
            # Increment the user's request count
            user_request_data[user_id]['count'] += 1
            save_user_request_data()

            assistant = get_or_create_assistant("default")
            thread = create_or_get_thread("default")

            assistant_response = None
            while not assistant_response:
                try:
                    client.beta.threads.messages.create(
                        thread_id=thread.id,
                        role="user",
                        content=message.content
                    )

                    run = client.beta.threads.runs.create(
                        thread_id=thread.id,
                        assistant_id=assistant.id
                    )

                    thread_messages = list(client.beta.threads.messages.list(thread_id=thread.id))

                    for msg in thread_messages:
                        if msg.role == "assistant":
                            assistant_response = msg
                            break
                except APIError as e:
                    logger.error(f"Error during assistant mode response: {e}")
                    if "Error code: 400" in str(e) and "Can't add messages to thread" in str(e):
                        logger.info("Waiting due to active run error")
                        time.sleep(2)
                    else:
                        raise e

            if assistant_response:
                await message.channel.send(assistant_response.content[0].text.value)
            else:
                await message.channel.send("No assistant response found.")
        except Exception as e:
            logger.error(f"Error during assistant mode response: {e}")
            await message.channel.send(f"Sorry, something went wrong: {e}")

    elif message.content.startswith("!make"):
        if user_request_data[user_id]['image_count'] >= IMAGE_REQUEST_LIMIT:
            wait_time = time_until_reset(user_id, 'last_image_reset')
            await message.channel.send(f"Sorry, you've reached the maximum number of image requests allowed for today. Please wait {wait_time} before trying again.")
            return

        try:
            user_request_data[user_id]['image_count'] += 1
            save_user_request_data()

            model = "dall-e-3"
            size = "512x512"

            prompt = message.content[len("!make "):].strip()
            response = client.images.generate(
                model=model,
                prompt=prompt,
                size=size,
                n=1
            )

            image_url = response.data[0].url
            await message.channel.send(f"Here is your generated image: {image_url}")

        except APIError as e:
            logger.error(f"OpenAI API returned an API Error: {e}")
            await message.channel.send(f"Sorry, there was an issue with the image generation service: {e}")
        except APIConnectionError as e:
            logger.error(f"Failed to connect to OpenAI API: {e}")
            await message.channel.send(f"Sorry, I couldn't connect to the image generation service: {e}")
        except RateLimitError as e:
            logger.error(f"OpenAI API request exceeded rate limit: {e}")
            await message.channel.send(f"Sorry, I'm receiving too many image requests at once: {e}")
        except AuthenticationError as e:
            logger.error(f"OpenAI API authentication error: {e}")
            await message.channel.send(f"Sorry, it looks like I've run out of credits: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            await message.channel.send(f"Sorry, something went wrong: {e}")

    elif message.content.startswith("!ass"):
        active_assistants[user_id] = True
        await message.channel.send("Assistant mode activated. I will respond to all your messages in this channel until you say 'stop', 'thanks', or 'done'.")

    if active_40kref_channel and message.channel.id == active_40kref_channel:
        if message.content.lower() == "!stop":
            active_40kref_channel = None
            await message.channel.send("Warhammer 40k Ref mode deactivated.")
        else:
            try:
                vector_store_id = get_or_create_vector_store()
                ensure_file_uploaded(vector_store_id, "40kCoreRules.txt")

                assistant = get_or_create_assistant("40kref", vector_store_id=vector_store_id)
                thread = create_or_get_thread("40kref")

                assistant_response = None
                while not assistant_response:
                    try:
                        client.beta.threads.messages.create(
                            thread_id=thread.id,
                            role="user",
                            content=message.content
                        )

                        run = client.beta.threads.runs.create(
                            thread_id=thread.id,
                            assistant_id=assistant.id
                        )

                        thread_messages = list(client.beta.threads.messages.list(thread_id=thread.id))

                        for msg in thread_messages:
                            if msg.role == "assistant":
                                assistant_response = msg
                                break
                    except APIError as e:
                        logger.error(f"Error during assistant mode response: {e}")
                        if "Error code: 400" in str(e) and "Can't add messages to thread" in str(e):
                            logger.info("Waiting due to active run error")
                            time.sleep(2)
                        else:
                            raise e

                if assistant_response:
                    await message.channel.send(assistant_response.content[0].text.value)
                else:
                    await message.channel.send("No assistant response found.")
            except Exception as e:
                logger.error(f"Error during 40kref mode response: {e}")
                await message.channel.send(f"Sorry, something went wrong: {e}")

    elif message.content.startswith("!40kref"):
        if active_40kref_channel is not None:
            await message.channel.send("Warhammer 40k Ref mode is already active in another channel.")
        else:
            active_40kref_channel = message.channel.id
            await message.channel.send("Warhammer 40k Ref mode activated. I will respond to all messages in this channel related to Warhammer 40k until someone says '!stop'.")

# Run your Discord bot
discord_client.run(os.getenv('DISCORD_BOT_TOKEN'))
