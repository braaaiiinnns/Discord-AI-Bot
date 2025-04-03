import logging
from utilities import compose_text_response, split_message, check_and_reset_user_count
from config import GPT_SYSTEM_PROMPT, GOOGLE_SYSTEM_PROMPT, CLAUDE_SYSTEM_PROMPT, DEFAULT_SUMMARY_LIMIT, SUMMARY_CHANNEL_ID, REQUEST_LIMIT, GOOGLE_GENAI_API_KEY
from state import BotState
from clients import get_google_genai_client

logger = logging.getLogger('discord_bot')

# Initialize bot_state and google_client
bot_state = BotState(timeout=3600)
google_client = get_google_genai_client(GOOGLE_GENAI_API_KEY)

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

async def handle_prompt_command(interaction, prompt, handler, client, description):
    """Handles the common logic for prompt-based commands."""
    logger.info(f"Handling {description} for user {interaction.user} with prompt: {prompt}")
    uid = str(interaction.user.id)
    bot_state.user_request_data = check_and_reset_user_count(uid, bot_state.user_request_data)
    
    await interaction.response.defer()
    try:
        # Get the result from the handler
        result = await handler(prompt, client, bot_state.user_request_data, REQUEST_LIMIT, uid)
        logger.info(f"Result for {description} (user {interaction.user}): {result}")
        full_response = compose_text_response(prompt, result)
        
        # Debugging: Log the channel IDs
        logger.debug(f"Interaction channel ID: {interaction.channel_id}")
        logger.debug(f"Summary channel ID: {SUMMARY_CHANNEL_ID}")
        
        # Check if the response exceeds the summary limit and is not in the summary channel
        if len(full_response) > DEFAULT_SUMMARY_LIMIT and int(interaction.channel_id) != int(SUMMARY_CHANNEL_ID):
            logger.info(f"Summarizing response for user {interaction.user}")
            summary = await summarize_response(full_response, google_client)
            await interaction.followup.send(summary)  # Send the summary to the user
            
            # Send the full response to the summary channel
            summary_channel = client.get_channel(SUMMARY_CHANNEL_ID)
            if summary_channel:
                logger.info(f"Sending full response to summary channel for user {interaction.user}")
                await summary_channel.send(f"**Original response for {interaction.user.mention}:**\n{full_response}")
            else:
                logger.error(f"Summary channel with ID {SUMMARY_CHANNEL_ID} not found.")
        else:
            # Send the full response to the user (split if too long)
            if len(full_response) > 2000:
                logger.info(f"Splitting long response for user {interaction.user}")
                for chunk in split_message(full_response):
                    await interaction.followup.send(chunk)
            else:
                await interaction.followup.send(full_response)
    except Exception as e:
        logger.error(f"Error in {description} for user {interaction.user}: {e}")
        await interaction.followup.send("An error occurred while processing your request. Please try again later.")

async def summarize_response(response: str, google_client) -> str:
    """Summarize the response to be under the DEFAULT_SUMMARY_LIMIT using Google GenAI."""
    logger.info("Summarizing response using Google GenAI")
    from config import DEFAULT_SUMMARY_LIMIT  # Import locally to avoid circular dependencies
    try:
        summary_prompt = f"Summarize the following text to less than {DEFAULT_SUMMARY_LIMIT} characters:\n\n{response}"
        summary = await handle_google_command_slash(summary_prompt, google_client, {}, 0, "summary")
        logger.info(f"Generated summary: {summary}")
        return summary.strip()
    except Exception as e:
        logger.error(f"Error summarizing response: {e}")
        return "Error summarizing response."
