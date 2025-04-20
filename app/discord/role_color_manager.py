import discord
import logging
import random
import datetime
import json
import os
import math
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
    
    def color_distance(self, color1, color2):
        """
        Calculate perceptual color distance between two colors.
        Returns a value between 0 and 100, where higher values indicate more distance.
        """
        # Extract RGB components
        r1, g1, b1 = color1
        r2, g2, b2 = color2
        
        # Calculate weighted Euclidean distance in RGB space
        # This is a simple perceptual color distance approximation
        # Humans are more sensitive to changes in green, less to blue
        r_weight = 0.3
        g_weight = 0.59
        b_weight = 0.11
        
        distance = math.sqrt(
            r_weight * (r1 - r2)**2 + 
            g_weight * (g1 - g2)**2 + 
            b_weight * (b1 - b2)**2
        )
        
        # Normalize to 0-100 scale
        return min(100, distance * 100 / 442)  # 442 is max possible weighted distance
    
    def is_color_distinct(self, new_color, previous_colors, other_colors, min_prev_distance=40, min_other_distance=30):
        """
        Check if a color is distinct from both the previous colors and other current colors.
        Returns True if the color is sufficiently different from all reference colors.
        
        Args:
            new_color: The new color to check
            previous_colors: List of previous colors for this role
            other_colors: List of colors being used by other roles today
            min_prev_distance: Minimum distance from previous colors
            min_other_distance: Minimum distance from other current colors
        """
        # Check distance from previous colors
        if previous_colors:
            for prev_color in previous_colors:
                prev_distance = self.color_distance(new_color, prev_color)
                if prev_distance < min_prev_distance:
                    return False
        
        # Check distance from other colors being used today
        for other_color in other_colors:
            other_distance = self.color_distance(new_color, other_color)
            if other_distance < min_other_distance:
                return False
        
        return True
    
    def generate_distinct_color(self, guild_id, role_id, role_index, total_roles):
        """
        Generate a color that is distinctly different from:
        1. The last 3 colors used for this role
        2. Colors assigned to other roles today
        
        Uses color theory and predefined palettes to ensure visual distinction.
        """
        color_key = f"{guild_id}_{role_id}"
        
        # Get up to the last 3 colors used for this role
        previous_colors = self.color_history.get(color_key, [])
        if len(previous_colors) > 3:
            previous_colors = previous_colors[-3:]  # Only consider the most recent 3 colors
            
        # Get colors already assigned to other roles in this update cycle
        other_colors_today = list(self.current_day_colors.values())
        
        # Predefined distinct color palette (expanded)
        distinct_colors = [
            (255, 0, 0),      # Red
            (0, 255, 0),      # Green
            (0, 0, 255),      # Blue
            (255, 255, 0),    # Yellow
            (255, 0, 255),    # Magenta
            (0, 255, 255),    # Cyan
            (255, 128, 0),    # Orange
            (128, 0, 255),    # Purple
            (255, 0, 128),    # Pink
            (0, 128, 255),    # Sky Blue
            (128, 255, 0),    # Lime
            (255, 128, 128),  # Light Red
            (128, 255, 128),  # Light Green
            (128, 128, 255),  # Light Blue
            (128, 64, 0),     # Brown
            (0, 128, 128),    # Teal
            (128, 0, 0),      # Maroon
            (0, 64, 0),       # Dark Green
        ]
        
        # If we have fewer roles than colors in our palette, we can just pick from the palette
        if total_roles <= len(distinct_colors):
            # Try to use a different color from the palette for each role
            base_color = distinct_colors[role_index % len(distinct_colors)]
            
            # Add some minor variation to make it interesting while keeping the base hue
            variation = 15  # Small variation to keep the same general color
            new_color = (
                max(0, min(255, base_color[0] + random.randint(-variation, variation))),
                max(0, min(255, base_color[1] + random.randint(-variation, variation))),
                max(0, min(255, base_color[2] + random.randint(-variation, variation)))
            )
            
            # Verify it's distinct enough from previous colors and other roles' colors
            if self.is_color_distinct(new_color, previous_colors, other_colors_today):
                return new_color
        
        # If we have more roles than palette colors or the palette color wasn't distinct enough,
        # try different approaches to generate distinct colors
        
        # Try up to 15 times to find a sufficiently different color
        for _ in range(15):
            # Randomly choose between approaches
            approach = random.randint(1, 3)
            
            if approach == 1 and previous_colors:
                # Complementary color approach - use the complement of the most recent color
                r, g, b = previous_colors[-1] if previous_colors else (128, 128, 128)
                new_color = (255 - r, 255 - g, 255 - b)
            elif approach == 2:
                # Pick from predefined distinct colors
                new_color = random.choice(distinct_colors)
                
                # Add some variation to avoid exact same colors from palette
                variation = 15
                new_color = (
                    max(0, min(255, new_color[0] + random.randint(-variation, variation))),
                    max(0, min(255, new_color[1] + random.randint(-variation, variation))),
                    max(0, min(255, new_color[2] + random.randint(-variation, variation)))
                )
            else:
                # Generate a completely random color
                new_color = (
                    random.randint(50, 255),
                    random.randint(50, 255),
                    random.randint(50, 255)
                )
            
            # Check if the new color is sufficiently different from both
            # the previous colors for this role and other roles' colors today
            if self.is_color_distinct(new_color, previous_colors, other_colors_today):
                return new_color
        
        # If we still haven't found a distinct color, use a fallback approach:
        # Take a color from our palette that's maximally different from existing colors
        
        max_distance = 0
        best_color = distinct_colors[0]
        
        for color in distinct_colors:
            # Calculate minimum distance to any existing color
            min_distance = 100  # Start with maximum possible
            
            for prev_color in previous_colors:
                prev_distance = self.color_distance(color, prev_color)
                min_distance = min(min_distance, prev_distance)
            
            for other_color in other_colors_today:
                other_distance = self.color_distance(color, other_color)
                min_distance = min(min_distance, other_distance)
            
            # If this color has a larger minimum distance, it's better
            if min_distance > max_distance:
                max_distance = min_distance
                best_color = color
        
        # Add a small variation to the best color
        variation = 10
        return (
            max(0, min(255, best_color[0] + random.randint(-variation, variation))),
            max(0, min(255, best_color[1] + random.randint(-variation, variation))),
            max(0, min(255, best_color[2] + random.randint(-variation, variation)))
        )
    
    async def change_role_colors(self):
        """Change role colors across all guilds"""
        logger.info(f"Running role color change at {datetime.datetime.now()}")
        
        # Clear the current day colors at the start of a new change cycle
        self.current_day_colors.clear()
        
        for guild in self.client.guilds:
            await self._change_role_colors_for_guild(guild)
            
        # Save updated colors
        self.save_previous_colors()
    
    async def _change_role_colors_for_guild(self, guild):
        """Change multiple role colors for a specific guild"""
        logger.info(f"Changing role colors for guild '{guild.name}'")
        
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
        
        # Update each role with a distinct color
        for i, role in enumerate(guild_roles):
            try:
                # Generate a distinct color for this role
                color_key = f"{guild.id}_{role.id}"
                rgb_color = self.generate_distinct_color(
                    guild.id, 
                    role.id,
                    i,  # Pass the role index
                    len(guild_roles)  # Pass the total number of roles
                )
                
                # Store the color used today
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
                await self._change_role_colors_for_guild(guild)
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
        """Change the color for a specific role in a guild"""
        logger.info(f"Changing color for specific role '{role_name}' in guild ID {guild_id}")
        
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
            # Generate a distinct color for this role
            color_key = f"{guild.id}_{role.id}"
            rgb_color = self.generate_distinct_color(
                guild.id,
                role.id,
                0,  # Single role, so index is 0
                1   # Only changing one role
            )
            
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
            
            return True, f"Changed role '{role_name}' color to RGB {rgb_color}"
        except Exception as e:
            error_msg = f"Error changing color for role '{role_name}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg
            
    def get_configured_role_names(self):
        """Return the list of role names configured for color changes"""
        return COLOR_CHANGE_ROLE_NAMES