import discord
import logging
from discord import app_commands
from config import GPT_SYSTEM_PROMPT, GOOGLE_SYSTEM_PROMPT, CLAUDE_SYSTEM_PROMPT
from state import BotState

class CommandGroup(app_commands.Group):  # Ensure proper inheritance from app_commands.Group
    """Command group for /ask commands."""
    def __init__(self, bot_state: BotState, logger: logging.Logger, client: discord.Client, openai_client, google_client, claude_client):
        super().__init__(name="ask", description="Ask various AI models")  # Ensure correct initialization
        self.bot_state = bot_state
        self.logger = logger
        self.client = client  # Store the client object
        self.openai_client = openai_client
        self.google_client = google_client
        self.claude_client = claude_client

    @app_commands.command(name="gpt", description="Ask GPT-4o-mini a question")
    async def ask_gpt(self, interaction: discord.Interaction, question: str):
        await self.handle_prompt_command(
            interaction, question, self.openai_client, "GPT-4o-mini", GPT_SYSTEM_PROMPT
        )

    @app_commands.command(name="google", description="Ask Google GenAI a question")
    async def ask_google(self, interaction: discord.Interaction, question: str):
        await self.handle_prompt_command(
            interaction, question, self.google_client, "Google GenAI", GOOGLE_SYSTEM_PROMPT
        )

    @app_commands.command(name="claude", description="Ask Claude (as a poet) a question")
    async def ask_claude(self, interaction: discord.Interaction, question: str):
        await self.handle_prompt_command(
            interaction, question, self.claude_client, "Claude", CLAUDE_SYSTEM_PROMPT
        )

    async def handle_prompt_command(self, interaction, prompt, client, description, system_prompt):
        """Handle a prompt-based command."""
        self.logger.info(f"Handling {description} for user {interaction.user} with prompt: {prompt}")
        uid = str(interaction.user.id)
        user_state = self.bot_state.get_user_state(uid)
        self.logger.debug(f"User state before adding prompt: {user_state.get_context()}")
        user_state.add_prompt("user", prompt)
        context = user_state.get_context()
        self.logger.debug(f"Context after adding user prompt: {context}")

        await interaction.response.defer()
        try:
            self.logger.info(f"Generating response for {description}...")
            result = await self.generate_response(context, client, system_prompt)
            user_state.add_prompt("assistant", result)
            self.logger.debug(f"User state after adding assistant response: {user_state.get_context()}")

            # Summarize the response if it exceeds the DEFAULT_SUMMARY_LIMIT
            from config import DEFAULT_SUMMARY_LIMIT, SUMMARY_CHANNEL_ID
            if len(result) > DEFAULT_SUMMARY_LIMIT:
                self.logger.info(f"Response exceeds {DEFAULT_SUMMARY_LIMIT} characters. Summarizing...")
                summary = await self.summarize_response(result, client)
                self.logger.debug("Generated summary successfully.")
                await interaction.followup.send(f"**Prompt:** {prompt}\n**Summary:** {summary}")

                # Send the full response to the summary channel or fallback to user
                summary_channel = self.client.get_channel(SUMMARY_CHANNEL_ID)  # Fetch channel by ID
                if summary_channel:
                    self.logger.info(f"Summary channel found: {summary_channel.name} (ID: {summary_channel.id})")
                    chunks = self.split_message(f"**Prompt:** {prompt}\n**Full Response:** {result}", limit=2000)
                    for chunk in chunks:
                        await summary_channel.send(chunk)
                    self.logger.info("Full response sent to summary channel.")
                else:
                    self.logger.error(f"Summary channel with ID {SUMMARY_CHANNEL_ID} not found.")
                    await interaction.followup.send("The summary channel is not available.")
            else:
                # Send the full response if it doesn't exceed the limit
                self.logger.info("Response is within the summary limit. Sending directly to the user.")
                chunks = self.split_message(f"**Prompt:** {prompt}\n**Full Response:** {result}", limit=2000)
                for chunk in chunks:
                    await interaction.followup.send(chunk)
        except Exception as e:
            self.logger.error(f"Error in {description} for user {interaction.user}: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while processing your request. Please try again later.")

    async def summarize_response(self, response: str, client):
        """Summarize the response to be under the DEFAULT_SUMMARY_LIMIT."""
        self.logger.info("Summarizing response...")
        from config import DEFAULT_SUMMARY_LIMIT
        summary_prompt = f"Summarize the following text to less than {DEFAULT_SUMMARY_LIMIT} characters:\n\n{response}"
        self.logger.debug("Summary prompt created successfully.")
        if hasattr(client, "models"):
            # Removed `await` since `generate_content` is synchronous
            summary_response = client.models.generate_content(
                model="gemini-2.0-flash", contents=summary_prompt
            )
            self.logger.debug("Summary response generated successfully.")
            return summary_response.text.strip()
        else:
            self.logger.error("Summarization is only supported for Google GenAI.")
            raise AttributeError("Summarization is only supported for Google GenAI.")

    def split_message(self, content: str, limit: int = 2000):
        """Split content into chunks of up to `limit` characters."""
        self.logger.debug(f"Splitting message into chunks of {limit} characters.")
        if len(content) <= limit:
            return [content]
        return [content[i:i + limit] for i in range(0, len(content), limit)]

    async def generate_response(self, context, client, system_prompt):
        """Generate a response using the provided client and system prompt."""
        self.logger.info("Generating response...")
        messages = [{"role": "system", "content": system_prompt}] + context
        self.logger.debug("Messages for response generation prepared successfully.")

        # Handle OpenAI client
        if hasattr(client, "chat"):
            self.logger.info("Using OpenAI client for response generation.")
            response = client.chat.completions.create(model="gpt-4o-mini", messages=messages)
            self.logger.debug("OpenAI response generated successfully.")
            return response.choices[0].message.content.strip()

        # Handle Google GenAI client
        elif hasattr(client, "models"):
            self.logger.info("Using Google GenAI client for response generation.")
            full_prompt = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])
            self.logger.debug("Full prompt for Google GenAI prepared successfully.")
            response = client.models.generate_content(
                model="gemini-2.0-flash", contents=full_prompt
            )
            self.logger.debug("Google GenAI response generated successfully.")
            return response.text.strip()

        # Handle Claude client
        elif hasattr(client, "messages"):
            self.logger.info("Using Claude client for response generation.")
            response = client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1000,
                temperature=1,
                system=system_prompt,
                messages=[{"type": "text", "text": msg["content"]} for msg in messages],
            )
            self.logger.debug("Claude response generated successfully.")
            content = response.content
            if isinstance(content, list):
                return "".join(item.text if hasattr(item, "text") else str(item) for item in content).strip()
            return content.strip()

        # Raise an error if the client is unsupported
        else:
            self.logger.error(f"Unsupported client type: {type(client).__name__}")
            raise AttributeError(f"Unsupported client type: {type(client).__name__}")


class CommandHandler:
    """Main command handler for registering commands."""
    def __init__(self, bot_state: BotState, tree: discord.app_commands.CommandTree):
        self.logger = logging.getLogger('discord_bot')  # Ensure consistent logger name
        self.bot_state = bot_state
        self.tree = tree

    def register_commands(self, client: discord.Client, openai_client, google_client, claude_client):
        try:
            # Register the /ask command group
            self.tree.add_command(CommandGroup(
                bot_state=self.bot_state,
                logger=self.logger,
                client=client,  # Pass the client object
                openai_client=openai_client,
                google_client=google_client,
                claude_client=claude_client
            ))
            self.logger.info("Registered /ask command group.")

            # Register the /clear_history command
            @self.tree.command(name="clear_history", description="Clear your conversation history")
            async def clear_history(interaction: discord.Interaction):
                self.logger.info(f"User {interaction.user} invoked /clear_history")
                uid = str(interaction.user.id)
                user_state = self.bot_state.get_user_state(uid)
                user_state.clear_history()
                self.logger.info(f"Cleared history for user {interaction.user}")
                await interaction.response.send_message("Your conversation history has been cleared.")
        except Exception as e:
            self.logger.error(f"Failed to register commands: {e}", exc_info=True)