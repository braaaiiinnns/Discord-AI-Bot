import logging
from utilities import time_until_reset, save_user_request_data
logger = logging.getLogger('discord_bot')

async def handle_ask_command_slash(prompt: str, openai_client, user_data, request_limit, user_id: str):
    if user_data[user_id]['count'] >= request_limit:
        wait_time = time_until_reset(user_data, user_id, 'last_reset')
        return f"Sorry, you've reached your request limit. Please wait {wait_time} before trying again."
    user_data[user_id]['count'] += 1
    save_user_request_data(user_data)
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()

async def handle_google_command_slash(prompt: str, google_client, user_data, request_limit, user_id: str):
    if user_data[user_id]['count'] >= request_limit:
        wait_time = time_until_reset(user_data, user_id, 'last_reset')
        return f"Sorry, you've reached your request limit. Please wait {wait_time} before trying again."
    user_data[user_id]['count'] += 1
    save_user_request_data(user_data)
    response = google_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )
    return response.text.strip()

async def handle_claude_command_slash(prompt: str, claude_client, user_data, request_limit, user_id: str):
    if user_data[user_id]['count'] >= request_limit:
        wait_time = time_until_reset(user_data, user_id, 'last_reset')
        return f"Sorry, you've reached your request limit. Please wait {wait_time} before trying again."
    user_data[user_id]['count'] += 1
    save_user_request_data(user_data)
    
    response = claude_client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1000,
        temperature=1,
        system="You are a world-class poet. Respond only with short poems.",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt}
                ]
            }
        ]
    )
    
    content = response.content
    if isinstance(content, list):
        # Convert each item using its 'text' attribute if available
        content = "".join(item.text if hasattr(item, "text") else str(item) for item in content)
    return content.strip()

async def handle_make_command_slash(prompt: str, openai_client):
    response = openai_client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        n=1
    )
    image_url = response.data[0].url
    return image_url