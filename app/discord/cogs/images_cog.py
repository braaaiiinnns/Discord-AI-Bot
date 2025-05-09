import discord
from discord import app_commands
from discord.ext import commands
import base64
import os
import uuid
import aiohttp
import io

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
            
    @app_commands.command(name="create", description="Generate an image using GPT-Image-1")
    async def create_image(self, interaction: discord.Interaction, prompt: str):
        """Generate an image using GPT-Image-1 and save it to file"""
        self.logger.info(f"User {interaction.user} requested GPT-Image-1 generation: {prompt}")
        await interaction.response.defer()
        
        try:
            # Generate the image using OpenAI's GPT-Image-1, strictly following the example
            self.logger.info("Generating image using GPT-Image-1...")
            response = self.openai_client.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                n=1,
                size="1024x1024"
            )
            
            # Process the response - the example shows the response has b64_json property
            try:
                # Get the base64 image data - this comes directly from the API
                image_data = response.data[0].b64_json
                image_bytes = base64.b64decode(image_data)
                
                # Generate a unique filename and save path
                filename = f"{uuid.uuid4().hex}.png"
                file_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "data", "files")
                os.makedirs(file_dir, exist_ok=True)
                filepath = os.path.join(file_dir, filename)
                
                # Save the image
                with open(filepath, "wb") as f:
                    f.write(image_bytes)
                
                self.logger.info(f"Image generated and saved successfully as {filename}")
                
                # Create a Discord file from the saved image
                discord_file = discord.File(filepath, filename=filename)
                
                # Send the image to the user
                await interaction.followup.send(
                    content=f"Here is your generated image using GPT-Image-1:\n**Prompt:** {prompt}",
                    file=discord_file
                )
            except AttributeError:
                # If b64_json is not found, try falling back to URL-based approach
                self.logger.warning("b64_json not found in response, attempting to use URL")
                try:
                    image_url = response.data[0].url
                    self.logger.info(f"Got image URL instead: {image_url}")
                    
                    # Send the image URL to the user
                    await interaction.followup.send(f"Here is your generated image using GPT-Image-1:\n**Prompt:** {prompt}\n\n{image_url}")
                except Exception as inner_e:
                    self.logger.error(f"Could not get image URL either: {inner_e}")
                    await interaction.followup.send("An error occurred while processing the generated image. Please try again later.")
                
        except Exception as e:
            self.logger.error(f"Error generating image with GPT-Image-1: {e}", exc_info=True)
            
            # Check for organization verification error
            error_msg = str(e)
            if "Your organization must be verified" in error_msg:
                await interaction.followup.send(
                    "Your OpenAI organization needs to be verified to use the GPT-Image-1 model. "
                    "Please try using the `/make` command instead, which uses DALL-E 3."
                )
            else:
                await interaction.followup.send(
                    "An error occurred while generating the image. Please try the `/make` command instead."
                )