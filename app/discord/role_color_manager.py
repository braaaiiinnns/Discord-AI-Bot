import discord
import logging
import datetime
import json
import os
import colorsys
from config.config import COLOR_CHANGE_ROLE_NAMES, COLOR_CHANGE_HOUR, COLOR_CHANGE_MINUTE, TIMEZONE, PREVIOUS_ROLE_COLORS_FILE, ROLE_COLOR_CYCLES_FILE
from app.discord.task_scheduler import TaskScheduler

logger = logging.getLogger('discord_bot')

class RoleColorManager:
    """Manages dynamic color changes for Discord roles"""
    
    def __init__(self, client=None, scheduler=None, logger=None):
        self.client = client
        self.scheduler = scheduler
        self.logger = logger or logging.getLogger(__name__)
        self.config_file = ROLE_COLOR_CYCLES_FILE
        self.previous_colors_file = PREVIOUS_ROLE_COLORS_FILE
        self.current_day_colors = {}
        
        # Load configuration with fallback to default
        self.role_configs = self.load_config()
        
        # Load previously stored colors if available
        self.previous_colors = self.load_previous_colors()
        
        # Dictionary to store color history for each role
        # Format: {color_key: [(r,g,b), (r,g,b), (r,g,b)]}
        self.color_history = {}
        
        # For the new hourly color algorithm
        self.color_change_task_hourly_id = None
    
    def load_config(self):
        """Load role color configuration"""
        # Currently not used, but allows for future customization
        return {}
    
    def load_previous_colors(self):
        """Load previous role colors from file"""
        if os.path.exists(self.previous_colors_file):
            try:
                with open(self.previous_colors_file, 'r') as f:
                    data = json.load(f)
                    
                    # Check if we have the new format with color history
                    if data is not None and 'colors' in data and 'history' in data:
                        self.previous_colors = data['colors']
                        self.color_history = data['history']
                    else:
                        # Old format, just colors
                        self.previous_colors = data if data is not None else {}
                        # Initialize color history with just the most recent color
                        for color_key, color in self.previous_colors.items():
                            self.color_history[color_key] = [color]
                            
                logger.info(f"Loaded previous colors from {self.previous_colors_file}")
                return self.previous_colors
            except Exception as e:
                logger.error(f"Error loading previous colors: {e}", exc_info=True)
                self.previous_colors = {}
                self.color_history = {}
                return {}
        else:
            # File doesn't exist yet
            self.previous_colors = {}
            self.color_history = {}
            return {}
    
    def save_previous_colors(self):
        """Save previous role colors to file"""
        try:
            # Save both the current colors and the history
            data = {
                'colors': self.previous_colors,
                'history': self.color_history
            }
            
            with open(self.previous_colors_file, 'w') as f:
                json.dump(data, f)
            logger.info(f"Saved previous colors to {self.previous_colors_file}")
        except Exception as e:
            logger.error(f"Error saving previous colors: {e}", exc_info=True)
    
    def start(self):
        """Register and start the role color change task"""
        # Schedule using the specified time from config
        time = datetime.time(hour=COLOR_CHANGE_HOUR, minute=COLOR_CHANGE_MINUTE)
        self.color_change_task_id = self.scheduler.schedule_at_time(
            self.change_role_colors, 
            time=time, 
            task_id="role_color_change",
            use_timezone=True  # Use the configured timezone
        )
        # Start the task
        self.scheduler.start_task(self.color_change_task_id)
        logger.info(f"Role color change scheduled with task ID: {self.color_change_task_id} at {time} {TIMEZONE}")
    
    def stop(self):
        """Stop the role color change task"""
        if self.color_change_task_id:
            self.scheduler.stop_task(self.color_change_task_id)
    
    def rgb_to_hsl(self, rgb):
        """Convert RGB color to HSL (Hue, Saturation, Lightness)"""
        r, g, b = rgb
        r /= 255
        g /= 255
        b /= 255
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        return h, s, l

    def hsl_to_rgb(self, hsl):
        """Convert HSL color to RGB"""
        h, s, l = hsl
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        return (int(r * 255), int(g * 255), int(b * 255))
    
    def get_time_based_color(self, guild_id, role_id):
        """
        Generate a color based on the current hour that cycles through the color wheel.
        - Hue: Cycles through the color wheel completely over 8 days
        - Saturation: Varies from minimum at midnight to maximum at noon
        - Lightness: Follows the sun cycle (lighter at sunrise, darker at sunset)
        """
        now = datetime.datetime.now()
        
        # Calculate hue based on days and hours (full cycle every 8 days = 192 hours)
        # 8 days = 192 hours = full color wheel (0-1)
        total_hours = (now.day * 24) + now.hour
        hue = (total_hours % 192) / 192  # Cycles 0-1 every 192 hours (8 days)
        
        # Saturation varies from minimum (0.3) at midnight to maximum (1.0) at noon
        # and back to minimum from noon to midnight
        hour = now.hour
        if hour <= 12:
            # 0h -> 0.3, 12h -> 1.0
            saturation = 0.3 + (hour / 12) * 0.7
        else:
            # 13h -> 0.94, 23h -> 0.36
            saturation = 1.0 - ((hour - 12) / 12) * 0.7
            
        # Lightness follows the sun cycle
        # Approximate sunrise/sunset times
        sunrise_hour = 6  # 6 AM
        sunset_hour = 18  # 6 PM
        
        if sunrise_hour <= hour < sunset_hour:
            # Daytime: lighter
            # Start lighter at sunrise, peak at noon, then start darkening
            if hour < (sunrise_hour + sunset_hour) / 2:
                # Sunrise to noon: gradually get lighter
                progress = (hour - sunrise_hour) / ((sunset_hour - sunrise_hour) / 2)
                lightness = 0.5 + (progress * 0.3)  # 0.5 to 0.8
            else:
                # Noon to sunset: gradually get darker
                progress = (hour - (sunrise_hour + sunset_hour) / 2) / ((sunset_hour - sunrise_hour) / 2)
                lightness = 0.8 - (progress * 0.3)  # 0.8 to 0.5
        else:
            # Nighttime: darker
            if hour < sunrise_hour:
                # Midnight to sunrise: gradually get lighter
                progress = hour / sunrise_hour
                lightness = 0.2 + (progress * 0.3)  # 0.2 to 0.5
            else:
                # Sunset to midnight: gradually get darker
                total_night_hours = (24 - sunset_hour) + sunrise_hour
                hours_since_sunset = (hour - sunset_hour)
                progress = hours_since_sunset / (total_night_hours / 2)
                if progress > 1:
                    progress = 1
                lightness = 0.5 - (progress * 0.3)  # 0.5 to 0.2
        
        # Create HSL color
        hsl_color = (hue, saturation, lightness)
        
        # Convert to RGB
        rgb_color = self.hsl_to_rgb(hsl_color)
        
        logger.info(f"Generated time-based color: HSL({hue:.2f}, {saturation:.2f}, {lightness:.2f}) -> RGB{rgb_color}")
        return rgb_color
        
    def start_hourly_changes(self):
        """Start the hourly role color change task"""
        # Stop any existing hourly task to prevent duplicates
        if self.color_change_task_hourly_id:
            self.scheduler.stop_task(self.color_change_task_hourly_id)
            
        # Every hour at minute 0
        self.color_change_task_hourly_id = self.scheduler.schedule_interval(
            self.change_role_colors_hourly,
            hours=1,  # Run once every hour
            task_id="hourly_role_color_change"
        )
        
        # NOTE: We don't start the task here - it will be started by the TaskManager
        # after the bot's event loop is running
        logger.info(f"Hourly role color change scheduled with task ID: {self.color_change_task_hourly_id} - will run every hour when started")
        
    def stop_hourly_changes(self):
        """Stop the hourly role color change task"""
        if self.color_change_task_hourly_id:
            self.scheduler.stop_task(self.color_change_task_hourly_id)
            
    async def change_role_colors_hourly(self, **kwargs):
        """Change role colors across all guilds using the time-based algorithm"""
        logger.info(f"Running hourly role color change at {datetime.datetime.now()}")
        
        # Clear the current colors at the start of a new change cycle
        self.current_day_colors.clear()
        
        for guild in self.client.guilds:
            await self._change_role_colors_hourly_for_guild(guild)
            
        # Save updated colors
        self.save_previous_colors()
        
    async def change_role_colors(self):
        """Change role colors across all guilds using the time-based algorithm"""
        logger.info(f"Running role color change at {datetime.datetime.now()}")
        
        # Clear the current day colors at the start of a new change cycle
        self.current_day_colors.clear()
        
        for guild in self.client.guilds:
            await self._change_role_colors_hourly_for_guild(guild)
            
        # Save updated colors
        self.save_previous_colors()
    
    async def _change_role_colors_for_guild(self, guild):
        """Change multiple role colors for a specific guild using time-based colors"""
        # Simply use the hourly method for consistency
        await self._change_role_colors_hourly_for_guild(guild)
        
    async def _change_role_colors_hourly_for_guild(self, guild):
        """Change multiple role colors for a specific guild using the time-based algorithm"""
        logger.info(f"Changing role colors hourly for guild '{guild.name}'")
        
        # Find all configured roles that exist in this guild
        guild_roles = []
        
        for role_name in COLOR_CHANGE_ROLE_NAMES:
            role = discord.utils.get(guild.roles, name=role_name.strip())
            if role:
                guild_roles.append(role)
            else:
                logger.warning(f"Role '{role_name}' not found in guild '{guild.name}'")
        
        if not guild_roles:
            logger.warning(f"No configured roles found in guild '{guild.name}'")
            return
        
        # Update each role with a time-based color
        for role in guild_roles:
            try:
                # Generate a time-based color for this role
                color_key = f"{guild.id}_{role.id}"
                rgb_color = self.get_time_based_color(guild.id, role.id)
                
                # Store the color used
                self.current_day_colors[color_key] = rgb_color
                
                # Convert to Discord color
                discord_color = discord.Color.from_rgb(*rgb_color)
                
                # Update the role color
                await role.edit(color=discord_color)
                logger.info(f"Changed role '{role.name}' color to {rgb_color} in guild '{guild.name}'")
                
                # Update color history for this role
                if color_key not in self.color_history:
                    self.color_history[color_key] = []
                self.color_history[color_key].append(rgb_color)
                
                # Store the new color as the previous color for next time
                self.previous_colors[color_key] = rgb_color
                
            except Exception as e:
                logger.error(f"Error changing color for role '{role.name}' in guild '{guild.name}': {e}", exc_info=True)
    
    async def change_role_color_now(self, guild_id=None):
        """Manually trigger a role color change"""
        logger.info(f"Manually triggering role color change")
        
        # Clear the current day colors at the start of a manual change
        self.current_day_colors.clear()
        
        if guild_id:
            guild = self.client.get_guild(guild_id)
            if guild:
                await self._change_role_colors_hourly_for_guild(guild)
                # Save updated colors
                self.save_previous_colors()
                return True
            else:
                logger.error(f"Guild with ID {guild_id} not found")
                return False
        else:
            # Change for all guilds
            await self.change_role_colors()
            return True
    
    async def change_specific_role_color(self, guild_id, role_name):
        """Change the color for a specific role in a guild using the time-based algorithm"""
        # Now using the time-based algorithm for all color changes
        return await self.change_specific_role_color_hourly(guild_id, role_name)
            
    def get_configured_role_names(self):
        """Return the list of role names configured for color changes"""
        return COLOR_CHANGE_ROLE_NAMES
    
    async def change_specific_role_color_hourly(self, guild_id, role_name):
        """Change the color for a specific role in a guild using the time-based algorithm"""
        logger.info(f"Changing color for specific role '{role_name}' in guild ID {guild_id} using hourly algorithm")
        
        # Get the guild
        guild = self.client.get_guild(guild_id)
        if not guild:
            logger.error(f"Guild with ID {guild_id} not found")
            return False, "Guild not found"
        
        # Find the specified role
        role = discord.utils.get(guild.roles, name=role_name.strip())
        if not role:
            logger.warning(f"Role '{role_name}' not found in guild '{guild.name}'")
            return False, f"Role '{role_name}' not found"
        
        try:
            # Generate a time-based color for this role
            color_key = f"{guild.id}_{role.id}"
            rgb_color = self.get_time_based_color(guild.id, role.id)
            
            # Store the color used
            self.current_day_colors[color_key] = rgb_color
            
            # Convert to Discord color
            discord_color = discord.Color.from_rgb(*rgb_color)
            
            # Update the role color
            await role.edit(color=discord_color)
            logger.info(f"Changed role '{role.name}' color to {rgb_color} in guild '{guild.name}'")
            
            # Update color history for this role
            if color_key not in self.color_history:
                self.color_history[color_key] = []
            self.color_history[color_key].append(rgb_color)
            
            # Store the new color as the previous color for next time
            self.previous_colors[color_key] = rgb_color
            self.save_previous_colors()
            
            return True, f"Changed role '{role_name}' color to RGB {rgb_color} using time-based algorithm"
        except Exception as e:
            error_msg = f"Error changing color for role '{role_name}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg