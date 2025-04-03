import logging
from utilities import compose_text_response, split_message, check_and_reset_user_count
from config import GPT_SYSTEM_PROMPT, GOOGLE_SYSTEM_PROMPT, CLAUDE_SYSTEM_PROMPT, DEFAULT_SUMMARY_LIMIT, SUMMARY_CHANNEL_ID, REQUEST_LIMIT, GOOGLE_GENAI_API_KEY


# Ensure DEFAULT_SUMMARY_LIMIT is explicitly imported and validated
if not isinstance(DEFAULT_SUMMARY_LIMIT, int) or DEFAULT_SUMMARY_LIMIT <= 0:
    raise ValueError("DEFAULT_SUMMARY_LIMIT must be a positive integer.")
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

async def handle_prompt_command(interaction, prompt, handler, client, description, google_client):
    """
    Handles the common logic for prompt-based commands.
    Calls the provided handler to generate a response, then routes it.
    """
    logger.info(f"Handling {description} for user {interaction.user} with prompt: {prompt}")
    uid = str(interaction.user.id)
    
    # Defer response immediately.
    await interaction.response.defer()
    try:
        result = await handler(prompt, client, {}, 0, uid)
        full_response = result  # Here you might combine context if needed.
        logger.info(f"Generated response for {description}: {full_response}")
        await route_response(interaction, prompt, full_response, google_client)
    except Exception as e:
        logger.error(f"Error in {description} for user {interaction.user}: {e}", exc_info=True)
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
        logger.error(f"Error summarizing response: {e}", exc_info=True)
        return "Error summarizing response."


async def route_response(interaction, prompt: str, full_response: str, google_client):
    """
    Routes the response based on length and channel:
      - If full_response is longer than DEFAULT_SUMMARY_LIMIT and the command wasn't used in the summary channel:
         1. Generate a summary and send it to the user.
         2. Post the full response to the summary channel.
      - Otherwise, send the full response (chunked if necessary) to the user.
    """
    # First, compose the text version (question + answer) if desired.
    combined = compose_text_response(prompt, full_response)
    
    # Check if we need to summarize.
    if len(combined) > DEFAULT_SUMMARY_LIMIT and int(interaction.channel_id) != int(SUMMARY_CHANNEL_ID):
        logger.info("Response exceeds summary limit; generating summary.")
        summary = await summarize_response(combined, google_client)
        summary_response = compose_text_response(prompt, summary)
        await interaction.followup.send(summary_response)
        
        # Now, post the full response in the summary channel.
        summary_channel = interaction.client.get_channel(SUMMARY_CHANNEL_ID)
        if summary_channel:
            logger.info(f"Posting full response to summary channel (ID: {SUMMARY_CHANNEL_ID}).")
            # If the full response is too long for a single message, split it.
            full_chunks = split_message(combined)
            for chunk in full_chunks:
                await summary_channel.send(chunk)
        else:
            try:
                # Attempt to fetch the channel from the API if not cached.
                summary_channel = await interaction.client.fetch_channel(SUMMARY_CHANNEL_ID)
            except Exception as e:
                logger.error(f"Failed to fetch summary channel: {e}", exc_info=True)
                logger.error(f"Summary channel with ID {SUMMARY_CHANNEL_ID} not found.")
            
            # Debugging: Log available guilds and channels
            logger.debug("Available guilds and channels:")
            for guild in interaction.client.guilds:
                logger.debug(f"Guild: {guild.name} (ID: {guild.id})")
                for channel in guild.channels:
                    logger.debug(f"  Channel: {channel.name} (ID: {channel.id})")
            # Fallback: send full response as followup messages.
            for chunk in split_message(combined):
                await interaction.followup.send(chunk)
    else:
        # Otherwise, just send the full response.
        if len(combined) > 2000:
            for chunk in split_message(combined):
                await interaction.followup.send(chunk)
        else:
            await interaction.followup.send(combined)