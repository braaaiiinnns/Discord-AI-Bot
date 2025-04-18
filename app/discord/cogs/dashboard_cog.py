import discord
from discord import app_commands
from discord.ext import commands

class Dashboard(commands.Cog):
    """Cog for dashboard access and management"""
    
    def __init__(self, bot, logger):
        self.bot = bot
        self.logger = logger
    
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