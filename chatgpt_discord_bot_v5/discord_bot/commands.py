
from discord_bot.utils import send_long_message
from openai.assistant import get_or_create_assistant, process_assistant_response
from openai.dalle import generate_dalle_image

async def handle_message(message, client):
    if message.author == client.user:
        return

    if message.content.startswith("!ask"):
        assistant = get_or_create_assistant("default")
        response = await process_assistant_response(assistant, message.content[len("!ask "):])
        await send_long_message(message.channel, response)
    elif message.content.startswith("!make"):
        image_url = generate_dalle_image(message.content[len("!make "):])
        await message.channel.send(embed=image_url)
