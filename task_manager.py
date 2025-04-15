import discord
import logging
import asyncio
import json
import os
import datetime
from discord import app_commands
from task_scheduler import TaskScheduler, ScheduleType
from role_color_manager import RoleColorManager

class TaskManager:
    """Centralized manager for all scheduled tasks in the Discord bot."""
    
    # Path to the tasks.json file
    TASKS_FILE = os.path.join(os.path.dirname(__file__), 'tasks.json')
    
    def __init__(self, client: discord.Client, scheduler: TaskScheduler, logger: logging.Logger):
        self.client = client
        self.scheduler = scheduler
        self.logger = logger
        self.task_ids = []  # Keep track of registered task IDs
        self.role_color_manager = None
        self.tasks_data = self._load_tasks()
        self.callback_registry = {}  # Registry mapping callback names to actual functions
        
    def _load_tasks(self) -> dict:
        """Load tasks from the JSON file, with support for comments."""
        try:
            if os.path.exists(self.TASKS_FILE):
                with open(self.TASKS_FILE, 'r') as f:
                    content = f.read()
                    # Remove JavaScript-style comments (both // and /* */)
                    import re
                    # Remove single-line comments
                    content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
                    # Remove multi-line comments
                    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
                    # Parse the cleaned JSON
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Error parsing JSON after comment removal: {e}")
                        # If still failing, try with a more lenient approach
                        import json5
                        try:
                            return json5.loads(content)
                        except Exception as e2:
                            self.logger.error(f"Error parsing with json5: {e2}")
                            raise e  # Re-raise the original error
            else:
                self.logger.warning(f"Tasks file not found at {self.TASKS_FILE}. Creating a new one.")
                default_data = {"tasks": []}
                self._save_tasks(default_data)
                return default_data
        except Exception as e:
            self.logger.error(f"Error loading tasks from JSON: {e}", exc_info=True)
            return {"tasks": []}
    
    def _save_tasks(self, tasks_data: dict = None) -> bool:
        """Save tasks to the JSON file."""
        try:
            if tasks_data is None:
                tasks_data = self.tasks_data
                
            with open(self.TASKS_FILE, 'w') as f:
                json.dump(tasks_data, f, indent=2)
            return True
        except Exception as e:
            self.logger.error(f"Error saving tasks to JSON: {e}", exc_info=True)
            return False
            
    def register_tasks(self, tree: app_commands.CommandTree):
        """Register all scheduled tasks and related commands."""
        self.logger.info("Registering scheduled tasks...")
        
        # Register standard callback functions with the registry
        self._register_standard_callbacks()
        
        # Register the remind_me command
        self._register_remind_me_command(tree)
        
        # Register the manage_tasks command
        self._register_task_management_commands(tree)
        
        self.logger.info(f"Successfully registered task-related commands")
    
    def _register_standard_callbacks(self):
        """Register standard callback functions that can be referenced in the JSON."""
        self.register_callback("example_interval_task", self.example_interval_task)
        
        # Will be registered if role_color_manager is set
        if self.role_color_manager:
            self.register_callback("change_role_colors", self.role_color_manager.change_role_colors)
            
        # Register the daily announcement function
        self.register_callback("send_daily_announcement", self.send_daily_announcement)
    
    def register_callback(self, name: str, callback_function):
        """Register a callback function with a name that can be referenced in the JSON."""
        self.callback_registry[name] = callback_function
        self.logger.info(f"Registered callback function: {name}")
    
    def register_role_color_manager(self, role_color_manager: RoleColorManager):
        """Register the role color manager with the task manager."""
        self.role_color_manager = role_color_manager
        # Register the color change callback
        self.register_callback("change_role_colors", role_color_manager.change_role_colors)
        self.logger.info("Registered role color manager with task manager")
    
    def start_tasks(self):
        """Start all tasks defined in the JSON configuration."""
        self.logger.info("Starting all enabled tasks from JSON configuration...")
        
        for task_config in self.tasks_data.get("tasks", []):
            # Skip disabled tasks
            if not task_config.get("enabled", True):
                self.logger.info(f"Skipping disabled task: {task_config.get('task_id')}")
                continue
                
            try:
                task_id = task_config.get("task_id")
                task_type = task_config.get("task_type")
                callback_name = task_config.get("callback")
                parameters = task_config.get("parameters", {})
                
                # Get the actual callback function from the registry
                callback_func = self.callback_registry.get(callback_name)
                if not callback_func:
                    self.logger.error(f"Callback function '{callback_name}' not registered for task '{task_id}'")
                    continue
                
                # Schedule based on task type
                if task_type == "interval":
                    registered_task_id = self.scheduler.schedule_interval(
                        callback_func,
                        hours=parameters.get("hours", 0),
                        minutes=parameters.get("minutes", 0),
                        seconds=parameters.get("seconds", 0),
                        task_id=task_id
                    )
                    self.task_ids.append(registered_task_id)
                    self.logger.info(f"Registered interval task: {task_id}")
                    
                elif task_type == "time":
                    time = datetime.time(
                        hour=parameters.get("hour", 0),
                        minute=parameters.get("minute", 0)
                    )
                    registered_task_id = self.scheduler.schedule_at_time(
                        callback_func,
                        time=time,
                        task_id=task_id,
                        use_timezone=parameters.get("use_timezone", True)
                    )
                    self.task_ids.append(registered_task_id)
                    self.logger.info(f"Registered time-based task: {task_id}")
                    
                elif task_type == "cron":
                    registered_task_id = self.scheduler.schedule_cron(
                        callback_func,
                        hour=parameters.get("hour"),
                        minute=parameters.get("minute"),
                        day_of_week=parameters.get("day_of_week"),
                        task_id=task_id,
                        use_timezone=parameters.get("use_timezone", True)
                    )
                    self.task_ids.append(registered_task_id)
                    self.logger.info(f"Registered cron task: {task_id}")
                    
                elif task_type == "wait":
                    # These are typically created at runtime, not at startup
                    self.logger.info(f"Wait task '{task_id}' will be scheduled on demand")
                    continue
                    
                else:
                    self.logger.error(f"Unknown task type '{task_type}' for task '{task_id}'")
                    continue
                    
            except Exception as e:
                self.logger.error(f"Error scheduling task '{task_config.get('task_id')}': {e}", exc_info=True)
        
        # Start registered tasks if they aren't already running
        for task_id in self.task_ids:
            try:
                # Check if the task exists in the scheduler and is not already running
                if task_id in self.scheduler.scheduled_tasks and not self.scheduler.scheduled_tasks[task_id].is_running():
                    self.scheduler.start_task(task_id)
                    self.logger.info(f"Started task: {task_id}")
                else:
                    self.logger.info(f"Task {task_id} is already running or doesn't exist")
            except Exception as e:
                self.logger.error(f"Error starting task {task_id}: {e}", exc_info=True)
    
    async def example_interval_task(self):
        """An example task that runs at an interval."""
        self.logger.info("Running example interval task")
        # This is just a placeholder method
    
    async def send_daily_announcement(self):
        """Sends a daily announcement to all servers."""
        self.logger.info("Sending daily announcement")
        try:
            announcement = "📢 Daily Announcement: Welcome to a new day with your friendly Discord bot!"
            
            for guild in self.client.guilds:
                # Try to find a general or announcements channel
                channel = discord.utils.get(guild.text_channels, name="general") or \
                          discord.utils.get(guild.text_channels, name="announcements") or \
                          discord.utils.get(guild.text_channels, name="bot-commands")
                
                if channel and channel.permissions_for(guild.me).send_messages:
                    await channel.send(announcement)
                    self.logger.info(f"Sent daily announcement to {guild.name} in #{channel.name}")
        except Exception as e:
            self.logger.error(f"Error sending daily announcement: {e}", exc_info=True)
    
    def _register_remind_me_command(self, tree: app_commands.CommandTree):
        """Register the remind_me command."""
        @tree.command(name="remind_me", description="Set a reminder for later")
        async def remind_me(interaction: discord.Interaction, 
                          hours: int = 0, 
                          minutes: int = 0,
                          message: str = "Reminder!"):
            
            self.logger.info(f"User {interaction.user} set a reminder for {hours}h {minutes}m: {message}")
            
            # Define a callback for the reminder
            async def send_reminder(user_id, channel_id, reminder_message):
                user = self.client.get_user(int(user_id))
                channel = self.client.get_channel(int(channel_id))
                if channel:
                    await channel.send(f"<@{user_id}> Reminder: {reminder_message}")
                    self.logger.info(f"Sent reminder to user {user_id}")
            
            # Schedule the reminder
            task_id = await self.scheduler.schedule_wait(
                send_reminder,
                hours=hours,
                minutes=minutes,
                user_id=str(interaction.user.id),
                channel_id=str(interaction.channel_id),
                reminder_message=message
            )
            
            total_minutes = hours * 60 + minutes
            await interaction.response.send_message(
                f"I'll remind you about '{message}' in {total_minutes} minutes!"
            )
            
            # Add the wait task to the JSON configuration
            self._add_wait_task_to_json(task_id, hours, minutes, message, interaction.user.id)
            
            self.logger.info(f"Registered reminder task with ID: {task_id}")
    
    def _add_wait_task_to_json(self, task_id, hours, minutes, message, user_id):
        """Add a wait task to the JSON configuration."""
        new_task = {
            "task_id": task_id,
            "task_type": "wait",
            "callback": "send_reminder",
            "description": f"Reminder for user {user_id}: {message}",
            "enabled": True,
            "parameters": {
                "hours": hours,
                "minutes": minutes,
                "user_id": str(user_id),
                "message": message,
                "created_at": datetime.datetime.now().isoformat()
            }
        }
        
        self.tasks_data["tasks"].append(new_task)
        self._save_tasks()
    
    def add_task(self, task_config):
        """Add a new task to the JSON configuration."""
        # Check if task with this ID already exists
        for i, task in enumerate(self.tasks_data["tasks"]):
            if task["task_id"] == task_config["task_id"]:
                # Replace existing task with the new configuration
                self.tasks_data["tasks"][i] = task_config
                self._save_tasks()
                return
        
        # No existing task found, add as new
        self.tasks_data["tasks"].append(task_config)
        self._save_tasks()
    
    def remove_task(self, task_id):
        """Remove a task from the JSON configuration."""
        self.tasks_data["tasks"] = [t for t in self.tasks_data["tasks"] if t["task_id"] != task_id]
        self._save_tasks()
        
        # Try to stop the task if it's running
        if task_id in self.task_ids:
            self.scheduler.stop_task(task_id)
            self.task_ids.remove(task_id)
    
    def update_task(self, task_id, enabled=None, parameters=None):
        """Update a task in the JSON configuration."""
        for task in self.tasks_data["tasks"]:
            if task["task_id"] == task_id:
                if enabled is not None:
                    task["enabled"] = enabled
                if parameters is not None:
                    task["parameters"].update(parameters)
                self._save_tasks()
                
                # Restart the task if it's currently registered
                if task_id in self.task_ids:
                    self.scheduler.restart_task(task_id)
                return True
        return False
    
    def _register_task_management_commands(self, tree: app_commands.CommandTree):
        """Register commands for managing tasks."""
        
        # Task list command
        @tree.command(name="list_tasks", description="List all scheduled tasks")
        @app_commands.default_permissions(administrator=True)
        async def list_tasks(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            
            if not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("You need administrator permissions to use this command.", ephemeral=True)
                return
                
            task_list = []
            for task in self.tasks_data.get("tasks", []):
                status = "✅ Enabled" if task.get("enabled", True) else "❌ Disabled"
                task_list.append(f"**{task['task_id']}** - {task['description']} - {status}")
            
            if not task_list:
                await interaction.followup.send("No scheduled tasks configured.", ephemeral=True)
                return
                
            # Split into chunks if needed to avoid Discord's message length limit
            chunks = [task_list[i:i+10] for i in range(0, len(task_list), 10)]
            
            for i, chunk in enumerate(chunks):
                header = "**Scheduled Tasks:**\n" if i == 0 else ""
                await interaction.followup.send(f"{header}{chr(10).join(chunk)}", ephemeral=True)
        
        # Enable/disable task command
        @tree.command(name="toggle_task", description="Enable or disable a scheduled task")
        @app_commands.default_permissions(administrator=True)
        async def toggle_task(
            interaction: discord.Interaction,
            task_id: str,
            enable: bool
        ):
            await interaction.response.defer(ephemeral=True)
            
            if not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("You need administrator permissions to use this command.", ephemeral=True)
                return
            
            # Update the task status
            success = self.update_task(task_id, enabled=enable)
            
            if success:
                status = "enabled" if enable else "disabled"
                await interaction.followup.send(f"Task '{task_id}' has been {status}.", ephemeral=True)
                
                # Restart or stop the task if it's currently active
                if task_id in self.task_ids:
                    if enable:
                        self.scheduler.restart_task(task_id)
                    else:
                        self.scheduler.stop_task(task_id)
            else:
                await interaction.followup.send(f"Task '{task_id}' not found.", ephemeral=True)
                
        # Add new task command (simplified version for common task types)
        @tree.command(name="add_interval_task", description="Add a new interval task")
        @app_commands.default_permissions(administrator=True)
        async def add_interval_task(
            interaction: discord.Interaction,
            task_id: str,
            callback: str,
            description: str,
            hours: int = 0,
            minutes: int = 0
        ):
            await interaction.response.defer(ephemeral=True)
            
            if not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("You need administrator permissions to use this command.", ephemeral=True)
                return
                
            # Validate callback exists
            if callback not in self.callback_registry:
                await interaction.followup.send(
                    f"Callback '{callback}' not found. Available callbacks: {', '.join(self.callback_registry.keys())}",
                    ephemeral=True
                )
                return
                
            # Create task config
            task_config = {
                "task_id": task_id,
                "task_type": "interval",
                "callback": callback,
                "description": description,
                "enabled": True,
                "parameters": {
                    "hours": hours,
                    "minutes": minutes,
                    "seconds": 0
                }
            }
            
            # Add the task
            self.add_task(task_config)
            
            # Schedule and start the task
            try:
                registered_task_id = self.scheduler.schedule_interval(
                    self.callback_registry[callback],
                    hours=hours,
                    minutes=minutes,
                    seconds=0,
                    task_id=task_id
                )
                self.task_ids.append(registered_task_id)
                self.scheduler.start_task(task_id)
                
                await interaction.followup.send(
                    f"Task '{task_id}' added and started. It will run every {hours}h {minutes}m.",
                    ephemeral=True
                )
            except Exception as e:
                self.logger.error(f"Error scheduling new task '{task_id}': {e}", exc_info=True)
                await interaction.followup.send(
                    f"Task added to configuration but failed to start: {str(e)}",
                    ephemeral=True
                )
        
        # Add the role color change command for administrators
        @tree.command(name="change_role_color", description="Change the color of a specific role")
        @app_commands.default_permissions(administrator=True)
        async def change_role_color(
            interaction: discord.Interaction,
            role_name: str = None
        ):
            await interaction.response.defer(ephemeral=True)
            
            # Check if user has administrator permissions
            if not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("You need administrator permissions to use this command.", ephemeral=True)
                return
            
            # Check if role color manager is initialized
            if not self.role_color_manager:
                await interaction.followup.send("Role color manager is not initialized.", ephemeral=True)
                return
            
            # Get the configured roles
            configured_roles = self.role_color_manager.get_configured_role_names()
            
            # If no role name is provided, list the available roles
            if not role_name:
                role_list = "\n".join([f"• {role}" for role in configured_roles])
                await interaction.followup.send(
                    f"**Configured roles for color change:**\n{role_list}\n\n"
                    f"Use `/change_role_color role_name:RoleName` to change a specific role's color.",
                    ephemeral=True
                )
                return
            
            # Check if the provided role is in the configured roles
            found = False
            for configured_role in configured_roles:
                if role_name.lower() == configured_role.lower().strip():
                    role_name = configured_role  # Use the exact case from configuration
                    found = True
                    break
            
            if not found:
                await interaction.followup.send(
                    f"Role '{role_name}' is not in the configured color change roles. "
                    f"Available roles are: {', '.join(configured_roles)}",
                    ephemeral=True
                )
                return
            
            # Change the role color
            success, message = await self.role_color_manager.change_specific_role_color(
                interaction.guild_id, 
                role_name
            )
            
            if success:
                await interaction.followup.send(
                    f"✅ {message}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ {message}",
                    ephemeral=True
                )