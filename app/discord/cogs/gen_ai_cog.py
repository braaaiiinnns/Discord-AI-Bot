import discord
from discord import app_commands
from discord.ext import commands
import time
# Add imports for Optional and Dict
from typing import Optional, Dict 
import logging # Import logging
from utils.ai_services import OpenAIStrategy, GoogleGenAIStrategy, ClaudeStrategy, GrokStrategy
from config.config import GPT_SYSTEM_PROMPT, GOOGLE_SYSTEM_PROMPT, CLAUDE_SYSTEM_PROMPT, GROK_SYSTEM_PROMPT, DEFAULT_SUMMARY_LIMIT
from utils.utilities import route_response
from app.discord.state import BotState # Import BotState
from app.discord.message_monitor import MessageMonitor # Import MessageMonitor

class AICogCommands(commands.Cog):
    """Cog for AI-related commands"""
    
    def __init__(self, bot, bot_state, response_channels, logger, message_monitor=None):
        self.bot = bot
        self.bot_state = bot_state
        self.response_channels = response_channels
        self.logger = logger
        self.message_monitor = message_monitor
        
        # AI clients
        self.openai_client = None
        self.google_client = None
        self.claude_client = None
        self.grok_client = None
        
        # Create the ask command group for app_commands
        self.ask_group = app_commands.Group(name="ask", description="Ask various AI models")
        
    def setup_clients(self, openai_client, google_client, claude_client, grok_client):
        """Setup AI clients"""
        self.openai_client = openai_client
        self.google_client = google_client
        self.claude_client = claude_client
        self.grok_client = grok_client
        
        # Register the commands in the group
        self._register_ask_commands()
        
        # Add the group to the command tree
        self.bot.tree.add_command(self.ask_group)
    
    def _register_ask_commands(self):
        """Register AI commands in the ask command group"""
        
        # GPT command
        @self.ask_group.command(name="gpt", description="Ask GPT-4o-mini a question")
        async def ask_gpt(interaction: discord.Interaction, question: str):
            await self._handle_ai_request(
                interaction, 
                question, 
                OpenAIStrategy(self.openai_client, self.logger),
                "GPT-4o-mini", 
                GPT_SYSTEM_PROMPT
            )
        
        # Google command
        @self.ask_group.command(name="google", description="Ask Google GenAI a question")
        async def ask_google(interaction: discord.Interaction, question: str):
            await self._handle_ai_request(
                interaction, 
                question, 
                GoogleGenAIStrategy(self.google_client, self.logger),
                "Google GenAI", 
                GOOGLE_SYSTEM_PROMPT
            )
        
        # Claude command
        @self.ask_group.command(name="claude", description="Ask Claude (as a poet) a question")
        async def ask_claude(interaction: discord.Interaction, question: str):
            await self._handle_ai_request(
                interaction, 
                question, 
                ClaudeStrategy(self.claude_client, self.logger),
                "Claude", 
                CLAUDE_SYSTEM_PROMPT
            )
        
        # Grok command
        @self.ask_group.command(name="grok", description="Ask Grok a witty question")
        async def ask_grok(interaction: discord.Interaction, question: str):
            await self._handle_ai_request(
                interaction, 
                question, 
                GrokStrategy(self.grok_client, self.logger),
                "Grok", 
                GROK_SYSTEM_PROMPT
            )
    
    # Only hybrid command - !ask - which uses Google's model
    @commands.command(name="ask", description="Ask Google GenAI a question")
    async def text_ask_google(self, ctx, *, question: str):
        """Ask a question to Google GenAI (text command)"""
        fake_interaction = await self._create_context_interaction(ctx)
        await self._handle_ai_request(
            fake_interaction,
            question,
            GoogleGenAIStrategy(self.google_client, self.logger),
            "Google GenAI", 
            GOOGLE_SYSTEM_PROMPT
        )
    
    async def _create_context_interaction(self, ctx):
        """
        Create a simple interaction-like object from a command context
        to reuse the existing interaction-based code
        """
        # Create a simple class that mimics the necessary Interaction properties
        class ContextBasedInteraction:
            def __init__(self, ctx):
                self.ctx = ctx
                self.user = ctx.author
                self.guild = ctx.guild
                self.channel_id = ctx.channel.id
                self.channel = ctx.channel
                self.guild_id = ctx.guild.id if ctx.guild else None
                self.response_sent = False
                
            async def response_proxy(self, content=None, embed=None, ephemeral=False):
                """Handle all interaction response methods needed"""
                return self
                
            async def response(self):
                """Mimic the interaction.response property"""
                return self
                
            async def defer(self):
                """Mimics the interaction.response.defer() method"""
                # Send a "thinking" message that we'll edit later
                self.message = await self.ctx.send("Thinking...")
                self.response_sent = True
                return self
                
            async def followup(self):
                """Mimics the interaction.followup property"""
                return self
                
            async def send(self, content=None, embed=None, ephemeral=False):
                """Mimics interaction.followup.send()"""
                if self.response_sent:
                    # Edit the "thinking" message instead of sending a new one
                    return await self.message.edit(content=content, embed=embed)
                else:
                    self.response_sent = True
                    return await self.ctx.send(content=content, embed=embed)
        
        # Create and return the fake interaction
        fake_interaction = ContextBasedInteraction(ctx)
        # Add necessary properties and methods
        fake_interaction.response = fake_interaction.response_proxy
        fake_interaction.followup = fake_interaction.followup
        return fake_interaction
    
    async def _handle_ai_request(self, interaction, prompt, strategy, model_name, system_prompt):
        """Handle an AI model request"""
        self.logger.info(f"Handling {model_name} request from user {interaction.user}: {prompt}")
        
        # Defer the response immediately to avoid timeout
        await interaction.response.defer()
        
        # Get user state and update context
        uid = str(interaction.user.id)
        user_state = self.bot_state.get_user_state(uid)
        user_state.add_prompt("user", prompt)
        context = user_state.get_context()
        
        try:
            # Record start time for performance tracking
            start_time = time.time()
            
            # Generate response using the appropriate strategy
            result = await strategy.generate_response(context, system_prompt)
            
            # Calculate execution time
            execution_time = time.time() - start_time
            
            # Update user state with the assistant's response
            user_state.add_prompt("assistant", result)
            
            # Log the AI interaction if message_monitor is available
            await self._log_ai_interaction(
                interaction,
                model_name,
                prompt,
                result,
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
    
    async def _log_ai_interaction(self, interaction: discord.Interaction, model: str, prompt: str, response: str, metadata: Optional[Dict] = None):
        """Log AI interaction details to the database via MessageMonitor."""
        # Use message_monitor if available
        if self.message_monitor:
            try:
                interaction_data = {
                    'user_id': str(interaction.user.id),
                    'user_name': interaction.user.name,
                    'guild_id': str(interaction.guild.id) if interaction.guild else '0',
                    'channel_id': str(interaction.channel.id) if interaction.channel else '0',
                    'model': model,
                    'prompt': prompt,
                    'response': response,
                    'metadata': metadata or {}
                    # timestamp and interaction_id are added by store_ai_interaction
                }
                # Use store_ai_interaction which exists in MessageMonitor
                await self.message_monitor.store_ai_interaction(interaction_data)
                self.logger.debug(f"AI interaction logged for user {interaction.user.name} using {model}")
            except Exception as e:
                self.logger.error(f"Failed to log AI interaction: {e}", exc_info=True)
        else:
            self.logger.warning("Message monitor not available, skipping AI interaction logging.")
    
    async def _summarize_response(self, response: str) -> str:
        """Summarize a response using Google GenAI"""
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