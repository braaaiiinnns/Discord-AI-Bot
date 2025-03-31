import logging
from utilities import time_until_reset, save_user_request_data, check_request_limit
from config import GPT_SYSTEM_PROMPT, GOOGLE_SYSTEM_PROMPT, CLAUDE_SYSTEM_PROMPT

logger = logging.getLogger('discord_bot')

# For OpenAI's GPT-4o-mini, include a system message.
async def handle_ask_command_slash(prompt: str, openai_client, user_data, request_limit, user_id: str):
    messages = [
        {"role": "system", "content": GPT_SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )
    return response.choices[0].message.content.strip()

# For Google GenAI, prepend the system prompt to the user prompt.
async def handle_google_command_slash(prompt: str, google_client, user_data, request_limit, user_id: str):
    full_prompt = f"{GOOGLE_SYSTEM_PROMPT}\n{prompt}"
    response = google_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=full_prompt
    )
    return response.text.strip()

# For Claude, pass the system prompt directly via the 'system' parameter.
async def handle_claude_command_slash(prompt: str, claude_client, user_data, request_limit, user_id: str):
    response = claude_client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1000,
        temperature=1,
        system=CLAUDE_SYSTEM_PROMPT,
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
        # Convert each item: use its 'text' attribute if available
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