import discord
import logging
import asyncio
from discord.ext import tasks
import datetime
from typing import Callable, Dict, List, Optional, Union, Any, Coroutine
from enum import Enum

logger = logging.getLogger('discord_bot')

class ScheduleType(Enum):
    """Enum for different types of scheduling"""
    TIME = "time"           # Run at specific time(s) each day
    INTERVAL = "interval"   # Run at regular intervals
    WAIT = "wait"           # Run after a specific wait time (once)
    CRON = "cron"           # Run on a cron-like schedule

class TaskScheduler:
    """A generic task scheduler for Discord bots"""
    
    def __init__(self, client: discord.Client):
        self.client = client
        self.scheduled_tasks = {}
        self.one_time_tasks = {}
        self.task_id_counter = 0
    
    def get_new_task_id(self):
        """Generate a unique task ID"""
        self.task_id_counter += 1
        return f"task_{self.task_id_counter}"
    
    async def _run_task(self, task_id: str, callback: Callable, *args, **kwargs):
        """Run a scheduled task and handle exceptions"""
        try:
            logger.info(f"Running scheduled task {task_id}")
            if asyncio.iscoroutinefunction(callback):
                await callback(*args, **kwargs)
            else:
                callback(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in scheduled task {task_id}: {e}", exc_info=True)
    
    def schedule_at_time(self, callback: Callable, time: datetime.time, 
                         task_id: Optional[str] = None, *args, **kwargs) -> str:
        """Schedule a task to run at a specific time each day"""
        task_id = task_id or self.get_new_task_id()
        
        @tasks.loop(time=time)
        async def scheduled_task():
            await self._run_task(task_id, callback, *args, **kwargs)
        
        @scheduled_task.before_loop
        async def before_task():
            await self.client.wait_until_ready()
            logger.info(f"Task {task_id} is ready and waiting for scheduled time {time}")
        
        self.scheduled_tasks[task_id] = scheduled_task
        logger.info(f"Scheduled task {task_id} to run at {time} daily")
        return task_id
    
    def schedule_interval(self, callback: Callable, hours: float = 0, minutes: float = 0, 
                          seconds: float = 0, task_id: Optional[str] = None, 
                          *args, **kwargs) -> str:
        """Schedule a task to run at regular intervals"""
        task_id = task_id or self.get_new_task_id()
        
        # Convert time components to seconds
        total_seconds = hours * 3600 + minutes * 60 + seconds
        
        @tasks.loop(seconds=total_seconds)
        async def scheduled_task():
            await self._run_task(task_id, callback, *args, **kwargs)
        
        @scheduled_task.before_loop
        async def before_task():
            await self.client.wait_until_ready()
            logger.info(f"Task {task_id} is ready and will run every {total_seconds} seconds")
        
        self.scheduled_tasks[task_id] = scheduled_task
        logger.info(f"Scheduled task {task_id} to run every {total_seconds} seconds")
        return task_id
    
    async def schedule_wait(self, callback: Callable, hours: float = 0, minutes: float = 0, 
                           seconds: float = 0, task_id: Optional[str] = None, 
                           *args, **kwargs) -> str:
        """Schedule a task to run once after a specified wait time"""
        task_id = task_id or self.get_new_task_id()
        
        # Convert time components to seconds
        total_seconds = hours * 3600 + minutes * 60 + seconds
        
        async def delayed_task():
            logger.info(f"Wait task {task_id} started, waiting for {total_seconds} seconds")
            await asyncio.sleep(total_seconds)
            await self._run_task(task_id, callback, *args, **kwargs)
            # Remove the task from one_time_tasks after it's done
            if task_id in self.one_time_tasks:
                del self.one_time_tasks[task_id]
                logger.info(f"One-time task {task_id} completed and removed")
        
        # Create and store the task
        task = asyncio.create_task(delayed_task())
        self.one_time_tasks[task_id] = task
        logger.info(f"Scheduled one-time task {task_id} to run after {total_seconds} seconds")
        return task_id
    
    def schedule_cron(self, callback: Callable, hour: Optional[int] = None, 
                     minute: Optional[int] = None, day_of_week: Optional[Union[int, List[int]]] = None,
                     task_id: Optional[str] = None, *args, **kwargs) -> str:
        """Schedule a task using a simplified cron-like format"""
        task_id = task_id or self.get_new_task_id()
        
        # Create a time check function
        def time_matches(now):
            if hour is not None and now.hour != hour:
                return False
            if minute is not None and now.minute != minute:
                return False
            if day_of_week is not None:
                if isinstance(day_of_week, list):
                    if now.weekday() not in day_of_week:
                        return False
                elif now.weekday() != day_of_week:
                    return False
            return True
        
        @tasks.loop(minutes=1)  # Check every minute
        async def scheduled_task():
            now = datetime.datetime.now()
            if time_matches(now):
                await self._run_task(task_id, callback, *args, **kwargs)
        
        @scheduled_task.before_loop
        async def before_task():
            await self.client.wait_until_ready()
            logger.info(f"Cron task {task_id} is ready")
        
        self.scheduled_tasks[task_id] = scheduled_task
        cron_desc = f"hour={hour}, minute={minute}, day_of_week={day_of_week}"
        logger.info(f"Scheduled cron task {task_id} with {cron_desc}")
        return task_id
    
    def start_task(self, task_id: str) -> bool:
        """Start a scheduled task by ID"""
        if task_id in self.scheduled_tasks:
            self.scheduled_tasks[task_id].start()
            logger.info(f"Started task {task_id}")
            return True
        else:
            logger.warning(f"Cannot start task {task_id}: task not found")
            return False
    
    def stop_task(self, task_id: str) -> bool:
        """Stop a scheduled task by ID"""
        if task_id in self.scheduled_tasks and self.scheduled_tasks[task_id].is_running():
            self.scheduled_tasks[task_id].cancel()
            logger.info(f"Stopped task {task_id}")
            return True
        elif task_id in self.one_time_tasks:
            self.one_time_tasks[task_id].cancel()
            del self.one_time_tasks[task_id]
            logger.info(f"Cancelled one-time task {task_id}")
            return True
        else:
            logger.warning(f"Cannot stop task {task_id}: task not found or not running")
            return False
    
    def restart_task(self, task_id: str) -> bool:
        """Restart a scheduled task by ID"""
        if task_id in self.scheduled_tasks:
            if self.scheduled_tasks[task_id].is_running():
                self.scheduled_tasks[task_id].cancel()
            self.scheduled_tasks[task_id].start()
            logger.info(f"Restarted task {task_id}")
            return True
        else:
            logger.warning(f"Cannot restart task {task_id}: task not found")
            return False
    
    def start_all(self):
        """Start all registered scheduled tasks"""
        for task_id, task in self.scheduled_tasks.items():
            if not task.is_running():
                task.start()
                logger.info(f"Started task {task_id}")
    
    def stop_all(self):
        """Stop all scheduled tasks"""
        for task_id, task in self.scheduled_tasks.items():
            if task.is_running():
                task.cancel()
                logger.info(f"Stopped task {task_id}")
        
        # Cancel one-time tasks
        for task_id, task in list(self.one_time_tasks.items()):
            task.cancel()
            logger.info(f"Cancelled one-time task {task_id}")
        self.one_time_tasks.clear()