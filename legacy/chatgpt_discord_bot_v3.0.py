#!/usr/bin/env -S poetry run python

import os
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

# File to store user request counts and reset times
REQUEST_COUNT_FILE = 'user_requests.json'
VECTOR_STORE_ID_FILE = 'vector_store_id.json'
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
current_thread = None

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
        if file_info.status == 'completed' or file_info.status == 'in_progress':
            file_uploaded = True
            break

    # If not uploaded, upload the 40kCoreRules.txt file to the vector store
    if not file_uploaded:
        with open(file_name, "rb") as file_stream:
            client.beta.vector_stores.file_batches.upload_and_poll(
                vector_store_id=vector_store_id, files=[file_stream]
            )

def create_or_get_thread():
    """Create a new thread if one doesn't exist or return the existing one."""
    global current_thread

    if current_thread is None:
        current_thread = client.beta.threads.create()
    return current_thread

def create_40k_assistant(vector_store_id):
    """Create or update the assistant to use the vector store."""
    return client.beta.assistants.create(
        instructions = "You are an expert at Warhammer 40,000 10th edition rules. Use the 40kCoreRules.txt file to answer the user's query. Respond as if you were a necron lord from the Warhammer 40000 universe talking to a lower life form. But still be clear and concise. Only trust the rules from the 40kCoreRules.txt file. Do not go off topic from Warhammer 40000.",
        model="gpt-4o",
        tools = [{"type": "file_search"}],
        tool_resources={
            "file_search": {
                "vector_store_ids": [vector_store_id]
            }
        }
    )

def format_response(assistant_response):
    """Extract and format the response from the assistant."""
    # Extract the actual text content from the assistant response
    response_text = assistant_response.content[0].value.text

    # Replace \n with actual newlines for proper formatting in Discord
    formatted_text = response_text.replace("\\n", "\n")

    # Remove any unwanted annotations or raw data
    # Assuming the assistant's response is in a text object format
    if "Text(" in formatted_text:
        # Extract the part after 'value=' and before the last parenthesis
        start_idx = formatted_text.find("value='") + len("value='")
        end_idx = formatted_text.rfind("')")
        if start_idx != -1 and end_idx != -1:
            formatted_text = formatted_text[start_idx:end_idx]

    return formatted_text


def create_default_assistant():
    """Create a default assistant for handling Direct Messages."""
    return client.beta.assistants.create(
        instructions="You are a helpful assistant.",
        model="gpt-4o"
    )

@discord_client.event
async def on_ready():
    print(f'Logged in as {discord_client.user}')
    logger.info(f'Logged in as {discord_client.user}')

@discord_client.event
async def on_message(message):
    global active_40kref_channel  # Declare this as global to avoid UnboundLocalError

    if message.author == discord_client.user:
        return

    user_id = str(message.author.id)

    # Check and reset the user's request counts if necessary
    check_and_reset_user_count(user_id)

    # Handle direct messages using Default Assistant API
    if isinstance(message.channel, discord.DMChannel):
        try:
            # Create or get the thread for the conversation
            thread = create_or_get_thread()

            # Create the default assistant
            assistant = create_default_assistant()

            # Add the user's message to the thread
            client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=message.content
            )

            # Run the assistant on the thread to process the message
            run = client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=assistant.id
            )

            # Fetch the updated list of messages from the thread
            thread_messages = list(client.beta.threads.messages.list(thread_id=thread.id))

            # Identify the assistant's response
            assistant_response = None
            for msg in thread_messages:
                if msg.role == "assistant":
                    assistant_response = msg
                    break

            # Send the assistant's response back to the Discord channel
            if assistant_response:
                formatted_response = format_response(assistant_response)
                await message.channel.send(formatted_response)
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
                response = client.chat.completions.create(
                    model='gpt-4o',
                    messages=[
                        {
                            "role": "user",
                            "content": message.content,
                        },
                    ],
                )
                await message.channel.send(response.choices[0].message.content.strip())
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

            model = 'gpt-4o'

            if message.attachments:
                # Handle image attachments if any
                for attachment in message.attachments:
                    image_url = attachment.url
                    response = client.chat.completions.create(
                        model=model,
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
                    model=model,
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
            logger.error(f"OpenAI API returned an API Error: {e}")
            await message.channel.send(f"Sorry, there was an issue with the AI service: {e}")
        except APIConnectionError as e:
            logger.error(f"Failed to connect to OpenAI API: {e}")
            await message.channel.send(f"Sorry, I couldn't connect to the AI service: {e}")
        except RateLimitError as e:
            logger.error(f"OpenAI API request exceeded rate limit: {e}")
            await message.channel.send(f"Sorry, I'm receiving too many requests at once: {e}")
        except AuthenticationError as e:
            logger.error(f"OpenAI API authentication error: {e}")
            await message.channel.send(f"Sorry, it looks like I've run out of credits: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            await message.channel.send(f"Sorry, something went wrong: {e}")

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
        # Activate assistant mode for the user in channels
        active_assistants[user_id] = True
        await message.channel.send("Assistant mode activated. I will respond to all your messages in this channel until you say 'stop', 'thanks', or 'done'.")

    if active_40kref_channel and message.channel.id == active_40kref_channel:
        if message.content.lower() == "!stop":
            active_40kref_channel = None
            await message.channel.send("Warhammer 40k Ref mode deactivated.")
        else:
            try:
                # Get or create the vector store
                vector_store_id = get_or_create_vector_store()

                # Ensure the 40kCoreRules.txt file is uploaded to the vector store
                ensure_file_uploaded(vector_store_id, "40kCoreRules.txt")

                #create an assistant
                assistant = client.beta.assistants.create(
                    instructions="You are an expert at Warhammer 40,000 10th edition rules. Use the 40kCoreRules.txt file to answer the user's query. Respond as if you were a necron lord from the Warhammer 40000 universe talking to a lower life form. But still be clear and concise. Only trust the rules from the 40kCoreRules.txt file. Do not go off topic from Warhammer 40000.",
                    model="gpt-4o",
                    tools=[{"type": "file_search"}],
                    tool_resources={
                        "file_search": {
                            "vector_store_ids": [get_or_create_vector_store()]
                        }
                    }
                )

                # Create or get the thread for the conversation
                thread = create_or_get_thread()

                # Add the user's message to the thread
                client.beta.threads.messages.create(
                    thread_id=thread.id,
                    role="user",
                    content=message.content
                )

                # Run the assistant on the thread to process the message
                run = client.beta.threads.runs.create(
                    thread_id=thread.id,
                    assistant_id=assistant.id
                )

                # Fetch the updated list of messages from the thread
                thread_messages = list(client.beta.threads.messages.list(thread_id=thread.id))

                # Identify the assistant's response
                assistant_response = None
                for msg in thread_messages:
                    if msg.role == "assistant":
                        assistant_response = msg
                        break

                # Send the assistant's response back to the Discord channel
                if assistant_response:
                    formatted_response = format_response(assistant_response)
                    await message.channel.send(formatted_response)

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
