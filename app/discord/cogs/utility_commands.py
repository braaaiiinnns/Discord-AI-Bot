import discord
from discord import app_commands
from discord.ext import commands

class UtilityCogCommands(commands.Cog):
    """Cog for utility commands"""
    
    def __init__(self, bot, bot_state, logger):
        self.bot = bot
        self.bot_state = bot_state
        self.logger = logger
        self.openai_client = None
    
    def setup_clients(self, openai_client):
        """Setup OpenAI client for image generation"""
        self.openai_client = openai_client
    
    @app_commands.command(name="clear_history", description="Clear your conversation history")
    async def clear_history(self, interaction: discord.Interaction):
        """Clear a user's conversation history"""
        self.logger.info(f"User {interaction.user} invoked /clear_history")
        uid = str(interaction.user.id)
        user_state = self.bot_state.get_user_state(uid)
        user_state.clear_history()
        self.logger.info(f"Cleared history for user {interaction.user}")
        await interaction.response.send_message("Your conversation history has been cleared.")
    
    @app_commands.command(name="make", description="Generate an image using DALL-E 3")
    async def make_image(self, interaction: discord.Interaction, prompt: str):
        """Generate an image using DALL-E 3"""
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
            image_url = response.data[0].url
            self.logger.info(f"Image generated successfully")
            
            # Send the image URL to the user
            await interaction.followup.send(f"Here is your generated image:\n{image_url}")
        except Exception as e:
            self.logger.error(f"Error generating image: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while generating the image. Please try again later.")
    
    @app_commands.command(name="dashboard", description="Get the URL to the bot's data dashboard")
    async def get_dashboard(self, interaction: discord.Interaction):
        """Get the URL to access the bot's dashboard"""
        self.logger.info(f"User {interaction.user} requested dashboard URL")
        
        # Check if we can access the dashboard from the client
        dashboard = None
        if hasattr(self.bot, 'dashboard') and self.bot.dashboard and self.bot.dashboard.running:
            dashboard_url = f"http://{self.bot.dashboard.host}:{self.bot.dashboard.port}"
            
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
            
    # Example of a cog listener for events
    @commands.Cog.listener()
    async def on_message(self, message):
        """
        Event listener example for messages.
        Only responds to "hello bot" to demonstrate cog listeners.
        """
        # Don't respond to bot messages to avoid loops
        if message.author.bot:
            return
            
        # Example of a listener that triggers on specific content
        if "hello bot" in message.content.lower():
            await message.channel.send(f"Hello {message.author.mention}! I'm listening to events in my utility cog.")