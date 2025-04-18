import discord
from discord import app_commands
from discord.ext import commands

class ImageGeneration(commands.Cog):
    """Cog for image generation using DALL-E"""
    
    def __init__(self, bot, logger):
        self.bot = bot
        self.logger = logger
        self.openai_client = None
    
    def setup_clients(self, openai_client):
        """Setup OpenAI client for image generation"""
        self.openai_client = openai_client
    
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