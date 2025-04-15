import discord
import logging
import time
from discord import app_commands
from utils.ai_services import OpenAIStrategy, GoogleGenAIStrategy, ClaudeStrategy, GrokStrategy
from config.config import GPT_SYSTEM_PROMPT, GOOGLE_SYSTEM_PROMPT, CLAUDE_SYSTEM_PROMPT, GROK_SYSTEM_PROMPT, DEFAULT_SUMMARY_LIMIT, ENCRYPTION_KEY
from app.discord.state import BotState
from utils.utilities import route_response
from utils.ai_logger import AIInteractionLogger

class BotCommands:
    """Handler for Discord bot commands"""
    
    def __init__(self, client: discord.Client, bot_state: BotState, tree: app_commands.CommandTree, 
                 response_channels: dict, logger: logging.Logger, ai_logger: AIInteractionLogger = None):
        self.client = client
        self.bot_state = bot_state
        self.tree = tree
        self.response_channels = response_channels
        self.logger = logger
        self.ai_logger = ai_logger
        
        # AI clients - will be initialized with register_commands
        self.openai_client = None
        self.google_client = None
        self.claude_client = None
        self.grok_client = None
    
    def register_commands(self, openai_client, google_client, claude_client, grok_client):
        """Register all Discord commands"""
        self.logger.info("Registering bot commands...")
        
        # Store AI clients
        self.openai_client = openai_client
        self.google_client = google_client
        self.claude_client = claude_client
        self.grok_client = grok_client
        
        # Register the ask command group
        self._register_ask_commands()
        
        # Register utility commands
        self._register_utility_commands()
        
        self.logger.info("All commands registered successfully")
    
    def _register_ask_commands(self):
        """Register the /ask command group"""
        ask_group = app_commands.Group(name="ask", description="Ask various AI models")
        
        # GPT command
        @ask_group.command(name="gpt", description="Ask GPT-4o-mini a question")
        async def ask_gpt(interaction: discord.Interaction, question: str):
            await self._handle_ai_request(
                interaction, 
                question, 
                OpenAIStrategy(self.openai_client, self.logger),
                "GPT-4o-mini", 
                GPT_SYSTEM_PROMPT
            )
        
        # Google command
        @ask_group.command(name="google", description="Ask Google GenAI a question")
        async def ask_google(interaction: discord.Interaction, question: str):
            await self._handle_ai_request(
                interaction, 
                question, 
                GoogleGenAIStrategy(self.google_client, self.logger),
                "Google GenAI", 
                GOOGLE_SYSTEM_PROMPT
            )
        
        # Claude command
        @ask_group.command(name="claude", description="Ask Claude (as a poet) a question")
        async def ask_claude(interaction: discord.Interaction, question: str):
            await self._handle_ai_request(
                interaction, 
                question, 
                ClaudeStrategy(self.claude_client, self.logger),
                "Claude", 
                CLAUDE_SYSTEM_PROMPT
            )
        
        # Grok command
        @ask_group.command(name="grok", description="Ask Grok a witty question")
        async def ask_grok(interaction: discord.Interaction, question: str):
            await self._handle_ai_request(
                interaction, 
                question, 
                GrokStrategy(self.grok_client, self.logger),
                "Grok", 
                GROK_SYSTEM_PROMPT
            )
        
        self.tree.add_command(ask_group)
        self.logger.info("Registered /ask command group")
    
    def _register_utility_commands(self):
        """Register utility commands"""
        
        # Clear history command
        @self.tree.command(name="clear_history", description="Clear your conversation history")
        async def clear_history(interaction: discord.Interaction):
            self.logger.info(f"User {interaction.user} invoked /clear_history")
            uid = str(interaction.user.id)
            user_state = self.bot_state.get_user_state(uid)
            user_state.clear_history()
            self.logger.info(f"Cleared history for user {interaction.user}")
            await interaction.response.send_message("Your conversation history has been cleared.")
        
        # Make image command
        @self.tree.command(name="make", description="Generate an image using DALL-E 3")
        async def make_image(interaction: discord.Interaction, prompt: str):
            self.logger.info(f"User {interaction.user} requested image generation: {prompt}")
            await interaction.response.defer()
            
            try:
                # Generate the image using OpenAI's DALL-E 3
                self.logger.info("Generating image using DALL-E 3...")
                response = self.openai_client.images.generate(
                    prompt=prompt,
                    n=1,  # Generate one image
                    size="1024x1024"  # Specify the image size
                )
                image_url = response['data'][0]['url']
                self.logger.info(f"Image generated successfully")
                
                # Send the image URL to the user
                await interaction.followup.send(f"Here is your generated image:\n{image_url}")
            except Exception as e:
                self.logger.error(f"Error generating image: {e}", exc_info=True)
                await interaction.followup.send("An error occurred while generating the image. Please try again later.")
        
        # Dashboard command to get the dashboard URL
        @self.tree.command(name="dashboard", description="Get the URL to the bot's data dashboard")
        async def get_dashboard(interaction: discord.Interaction):
            self.logger.info(f"User {interaction.user} requested dashboard URL")
            
            # Check if we can access the dashboard from the client
            dashboard = None
            if hasattr(self.client, 'dashboard') and self.client.dashboard and self.client.dashboard.running:
                dashboard_url = f"http://{self.client.dashboard.host}:{self.client.dashboard.port}"
                
                # Respond with the URL (ephemeral message for privacy)
                embed = discord.Embed(
                    title="📊 Bot Dashboard",
                    description=f"Access the data dashboard at: [Dashboard Link]({dashboard_url})",
                    color=discord.Color.blue()
                )
                embed.add_field(
                    name="What's in the Dashboard?", 
                    value="• Message activity statistics\n• User engagement metrics\n• File storage analytics\n• AI interaction data"
                )
                embed.set_footer(text="Data updates every 60 seconds. Optimized for log(n) access.")
                
                # Make the message ephemeral so only the command user can see it
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                # Dashboard is not available
                await interaction.response.send_message(
                    "⚠️ The dashboard is not currently available. Please contact the bot administrator.",
                    ephemeral=True
                )
        
        self.logger.info("Registered utility commands")
    
    async def _handle_ai_request(self, interaction: discord.Interaction, prompt: str, 
                                 strategy, model_name: str, system_prompt: str):
        """Handle an AI model request"""
        self.logger.info(f"Handling {model_name} request from user {interaction.user}: {prompt}")
        
        # Get user state and update context
        uid = str(interaction.user.id)
        user_state = self.bot_state.get_user_state(uid)
        user_state.add_prompt("user", prompt)
        context = user_state.get_context()
        
        await interaction.response.defer()
        
        try:
            # Record start time for performance tracking
            start_time = time.time()
            
            # Generate response using the appropriate strategy
            self.logger.info(f"Generating response using {model_name}...")
            result = await strategy.generate_response(context, system_prompt)
            
            # Calculate execution time
            execution_time = time.time() - start_time
            
            # Update user state with the assistant's response
            user_state.add_prompt("assistant", result)
            
            # Log the AI interaction if logger is available
            if self.ai_logger:
                guild_id = interaction.guild.id if interaction.guild else "DM"
                await self.ai_logger.log_interaction(
                    user_id=uid,
                    guild_id=guild_id,
                    channel_id=interaction.channel_id,
                    model=model_name,
                    prompt=prompt,
                    response=result,
                    execution_time=execution_time,
                    metadata={
                        "system_prompt": system_prompt,
                        "context_length": len(context),
                        "channel_name": interaction.channel.name if hasattr(interaction.channel, "name") else "DM",
                        "user_name": f"{interaction.user.name}#{interaction.user.discriminator}" if hasattr(interaction.user, "discriminator") else interaction.user.name
                    }
                )
            
            # Determine if summarization is needed
            summary = None
            if len(result) > DEFAULT_SUMMARY_LIMIT:
                self.logger.info(f"Response exceeds {DEFAULT_SUMMARY_LIMIT} characters. Summarizing...")
                summary = await self._summarize_response(result)
            
            # Route the response
            await route_response(
                interaction, 
                prompt, 
                result, 
                summary, 
                self.response_channels, 
                self.logger
            )
        except Exception as e:
            self.logger.error(f"Error in {model_name} response generation: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while processing your request. Please try again later.")
    
    async def _summarize_response(self, response: str) -> str:
        """Summarize a response using Google GenAI"""
        self.logger.info("Summarizing response...")
        summary_prompt = f"Summarize the following text to less than {DEFAULT_SUMMARY_LIMIT} characters:\n\n{response}"
        
        try:
            google_strategy = GoogleGenAIStrategy(self.google_client, self.logger)
            return await google_strategy.generate_response(
                [{"role": "user", "content": summary_prompt}], 
                GOOGLE_SYSTEM_PROMPT
            )
        except Exception as e:
            self.logger.error(f"Error during summarization: {e}", exc_info=True)
            # Return a basic summary if the smart summarization fails
            return response[:DEFAULT_SUMMARY_LIMIT] + "... (truncated)"