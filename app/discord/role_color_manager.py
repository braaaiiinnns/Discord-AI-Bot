import discord
import logging
import random
import datetime
import json
import os
import math
from config.config import COLOR_CHANGE_ROLE_NAMES, COLOR_CHANGE_HOUR, COLOR_CHANGE_MINUTE, TIMEZONE
from app.discord.task_scheduler import TaskScheduler

logger = logging.getLogger('discord_bot')

# File to store previous colors
PREVIOUS_COLORS_FILE = 'previous_role_colors.json'

class RoleColorManager:
    """Manages role color changes using the generic TaskScheduler"""
    
    def __init__(self, client, scheduler: TaskScheduler):
        self.client = client
        self.scheduler = scheduler
        self.color_change_task_id = None
        self.previous_colors = {}
        self.current_day_colors = {}  # Track colors used on the current day
        self.load_previous_colors()
    
    def load_previous_colors(self):
        """Load previous role colors from file"""
        if os.path.exists(PREVIOUS_COLORS_FILE):
            try:
                with open(PREVIOUS_COLORS_FILE, 'r') as f:
                    self.previous_colors = json.load(f)
                logger.info(f"Loaded previous colors from {PREVIOUS_COLORS_FILE}")
            except Exception as e:
                logger.error(f"Error loading previous colors: {e}", exc_info=True)
                self.previous_colors = {}
    
    def save_previous_colors(self):
        """Save previous role colors to file"""
        try:
            with open(PREVIOUS_COLORS_FILE, 'w') as f:
                json.dump(self.previous_colors, f)
            logger.info(f"Saved previous colors to {PREVIOUS_COLORS_FILE}")
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
    
    def is_color_distinct(self, new_color, previous_color, other_colors, min_prev_distance=40, min_other_distance=30):
        """
        Check if a color is distinct from both the previous color and other current colors.
        Returns True if the color is sufficiently different from all reference colors.
        """
        # Check distance from previous color
        if previous_color:
            prev_distance = self.color_distance(new_color, previous_color)
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
        1. The previous color for this role
        2. Colors assigned to other roles today
        
        Uses color theory and predefined palettes to ensure visual distinction.
        """
        color_key = f"{guild_id}_{role_id}"
        previous_rgb = self.previous_colors.get(color_key)
        
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
            
            # Verify it's distinct enough
            if self.is_color_distinct(new_color, previous_rgb, other_colors_today):
                return new_color
        
        # If we have more roles than palette colors or the palette color wasn't distinct enough,
        # try different approaches to generate distinct colors
        
        # Try up to 15 times to find a sufficiently different color
        for _ in range(15):
            # Randomly choose between approaches
            approach = random.randint(1, 3)
            
            if approach == 1 and previous_rgb:
                # Complementary color approach
                r, g, b = previous_rgb
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
            # the previous color for this role and other roles' colors today
            if self.is_color_distinct(new_color, previous_rgb, other_colors_today):
                return new_color
        
        # If we still haven't found a distinct color, use a fallback approach:
        # Take a color from our palette that's maximally different from existing colors
        
        max_distance = 0
        best_color = distinct_colors[0]
        
        for color in distinct_colors:
            # Calculate minimum distance to any existing color
            min_distance = 100  # Start with maximum possible
            
            if previous_rgb:
                prev_distance = self.color_distance(color, previous_rgb)
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