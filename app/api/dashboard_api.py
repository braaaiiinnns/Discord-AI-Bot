"""
Dashboard API for the Discord Bot.
Provides endpoints to access bot statistics and data.
"""

import logging
import json
import os
import discord # Import discord for type hints and utilities
from flask import Blueprint, jsonify, request, current_app
from flask_cors import CORS
# from flask_login import login_required # Removed old login decorator
from .auth import require_api_key # Import the new API key decorator
from ..discord.message_monitor import MessageMonitor
from .data_service import APIDataService # Use our new data service
from utils.logger import setup_logger
from config.config import (
    MESSAGE_LISTENERS_FILE, PREMIUM_ROLES_FILE, 
    PREVIOUS_ROLE_COLORS_FILE, ROLE_COLOR_CYCLES_FILE,
    TASKS_FILE
)

# Set up logger
logger = setup_logger('discord_bot.api.dashboard')

# Create Blueprint
dashboard_bp = Blueprint('dashboard_api', __name__, url_prefix='/api') # Changed prefix to /api

# Enable CORS for the blueprint
CORS(dashboard_bp)

# Store references
bot_instance = None
data_service = None

def initialize(bot):
    """Initialize the API with a reference to the bot instance"""
    global bot_instance, data_service
    bot_instance = bot
    if hasattr(bot, 'message_monitor') and bot.message_monitor:
        data_service = APIDataService(bot.message_monitor.get_database())
    else:
        data_service = None
        logger.warning("Message monitor not found. Data service endpoints might fail.")
    logger.info("API initialized with bot instance")

# --- Existing Endpoints (under /api/dashboard/) ---
# Note: Routes are adjusted to be under /api/dashboard/

@dashboard_bp.route('/dashboard/health', methods=['GET'])
# No API key needed for health check
def health_check():
    """Simple health check endpoint"""
    return jsonify({
        "status": "healthy",
        "message": "API is running"
    })

@dashboard_bp.route('/dashboard/summary', methods=['GET'])
@require_api_key # Add API key protection
async def summary():
    """Get summary statistics for all guilds or a specific guild"""
    try:
        guild_id = request.args.get('guild_id')
        filter_criteria = {"guild_id": guild_id} if guild_id else None
        
        # Use mock data for testing if needed
        use_mock = request.args.get('mock', 'false').lower() == 'true'
        
        if use_mock:
            data = get_mock_data()
            logger.debug("Returning mock data for summary endpoint")
        else:
            data = await data_service.get_dashboard_summary(filter_criteria) if data_service else None
            logger.debug(f"Fetched dashboard summary data: {type(data)}")
        
        if not data:
            data = get_mock_data()  # Fallback to mock data
            logger.warning("No data from data_service, using mock data instead")
        
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error in summary endpoint: {str(e)}", exc_info=True)
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500

@dashboard_bp.route('/dashboard/messages', methods=['GET'])
@require_api_key # Add API key protection
async def messages():
    """Get message statistics"""
    try:
        guild_id = request.args.get('guild_id')
        days = int(request.args.get('days', 30))
        filter_criteria = {"guild_id": guild_id} if guild_id else None
        
        # Use mock data for testing if needed
        use_mock = request.args.get('mock', 'false').lower() == 'true'
        
        if use_mock:
            data = get_mock_message_data()
            logger.debug("Returning mock data for messages endpoint")
        else:
            data = await data_service.get_message_stats(filter_criteria, days) if data_service else None
            logger.debug(f"Fetched message stats data: {type(data)}")
        
        if not data:
            data = get_mock_message_data()  # Fallback to mock data
            logger.warning("No data from data_service, using mock data instead")
        
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error in messages endpoint: {str(e)}", exc_info=True)
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500

@dashboard_bp.route('/dashboard/users', methods=['GET'])
@require_api_key # Add API key protection
async def users():
    """Get user statistics"""
    try:
        guild_id = request.args.get('guild_id')
        limit = int(request.args.get('limit', 10))
        filter_criteria = {"guild_id": guild_id} if guild_id else None
        
        # Use mock data for testing if needed
        use_mock = request.args.get('mock', 'false').lower() == 'true'
        
        if use_mock:
            data = get_mock_user_data()
            logger.debug("Returning mock data for users endpoint")
        else:
            data = await data_service.get_user_stats(filter_criteria, limit) if data_service else None
            logger.debug(f"Fetched user stats data: {type(data)}")
        
        if not data:
            data = get_mock_user_data()  # Fallback to mock data
            logger.warning("No data from data_service, using mock data instead")
        
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error in users endpoint: {str(e)}", exc_info=True)
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500

@dashboard_bp.route('/dashboard/ai', methods=['GET'])
@require_api_key # Add API key protection
async def ai_interactions():
    """Get AI interaction statistics"""
    try:
        guild_id = request.args.get('guild_id')
        days = int(request.args.get('days', 30))
        filter_criteria = {"guild_id": guild_id} if guild_id else None
        
        # Use mock data for testing if needed
        use_mock = request.args.get('mock', 'false').lower() == 'true'
        
        if use_mock:
            data = get_mock_ai_data()
            logger.debug("Returning mock data for AI endpoint")
        else:
            data = await data_service.get_ai_stats(filter_criteria, days) if data_service else None
            logger.debug(f"Fetched AI stats data: {type(data)}")
        
        if not data:
            data = get_mock_ai_data()  # Fallback to mock data
            logger.warning("No data from data_service, using mock data instead")
        
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error in AI endpoint: {str(e)}", exc_info=True)
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500

@dashboard_bp.route('/dashboard/guilds', methods=['GET'])
@require_api_key # Add API key protection
def guilds():
    """Get list of available guilds"""
    try:
        # Use bot_instance instead of the undefined message_monitor variable
        if not bot_instance or not hasattr(bot_instance, 'message_monitor') or not bot_instance.message_monitor.client:
            logger.warning("Bot instance or message monitor not available. Returning mock data.")
            return jsonify(get_mock_guilds())
        
        guild_list = []
        for guild in bot_instance.message_monitor.client.guilds:
            guild_list.append({
                "id": str(guild.id),
                "name": guild.name,
                "icon": guild.icon.url if guild.icon else None,
                "member_count": guild.member_count
            })
        
        logger.debug(f"Returning {len(guild_list)} guilds")
        return jsonify(guild_list)
    except Exception as e:
        logger.error(f"Error in guilds endpoint: {str(e)}", exc_info=True)
        return jsonify(get_mock_guilds())

@dashboard_bp.route('/dashboard/data/all/messages', methods=['GET'])
@require_api_key # Add API key protection
async def get_all_messages_data():
    """API endpoint to get all messages."""
    try:
        # Use global data_service instead of current_app.config
        if not data_service:
            logger.error("Data service is not initialized")
            return jsonify({"error": "Data service not available", "mock": True}), 500
            
        data = await data_service.get_all_messages()
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error fetching all messages data: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch data", "details": str(e)}), 500

@dashboard_bp.route('/dashboard/data/all/files', methods=['GET'])
@require_api_key # Add API key protection
async def get_all_files_data():
    """API endpoint to get all files."""
    try:
        # Use global data_service instead of current_app.config
        if not data_service:
            logger.error("Data service is not initialized")
            return jsonify({"error": "Data service not available", "mock": True}), 500
            
        data = await data_service.get_all_files()
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error fetching all files data: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch data", "details": str(e)}), 500

@dashboard_bp.route('/dashboard/data/all/reactions', methods=['GET'])
@require_api_key # Add API key protection
async def get_all_reactions_data():
    """API endpoint to get all reactions."""
    try:
        # Use global data_service instead of current_app.config
        if not data_service:
            logger.error("Data service is not initialized")
            return jsonify({"error": "Data service not available", "mock": True}), 500
            
        data = await data_service.get_all_reactions()
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error fetching all reactions data: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch data", "details": str(e)}), 500

@dashboard_bp.route('/dashboard/data/all/message_edits', methods=['GET'])
@require_api_key # Add API key protection
async def get_all_message_edits_data():
    """API endpoint to get all message edits."""
    try:
        # Use global data_service instead of current_app.config
        if not data_service:
            logger.error("Data service is not initialized")
            return jsonify({"error": "Data service not available", "mock": True}), 500
            
        data = await data_service.get_all_message_edits()
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error fetching all message edits data: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch data", "details": str(e)}), 500
        
@dashboard_bp.route('/dashboard/data/all/channels', methods=['GET'])
@require_api_key # Add API key protection
async def get_all_channels_data():
    """API endpoint to get all channels."""
    try:
        # Use global data_service instead of current_app.config
        if not data_service:
            logger.error("Data service is not initialized")
            return jsonify({"error": "Data service not available", "mock": True}), 500
            
        data = await data_service.get_all_channels()
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error fetching all channels data: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch data", "details": str(e)}), 500

@dashboard_bp.route('/dashboard/data/all/ai_interactions', methods=['GET'])
@require_api_key # Add API key protection
async def get_all_ai_interactions_data():
    """API endpoint to get all AI interactions."""
    try:
        # Use global data_service instead of current_app.config
        if not data_service:
            logger.error("Data service is not initialized")
            return jsonify({"error": "Data service not available", "mock": True}), 500
            
        data = await data_service.get_all_ai_interactions()
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error fetching all AI interactions data: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch data", "details": str(e)}), 500

# Endpoints for JSON data files
@dashboard_bp.route('/dashboard/data/json/message_listeners', methods=['GET'])
@require_api_key # Add API key protection
async def get_message_listeners_json():
    data = read_json_file(MESSAGE_LISTENERS_FILE)
    return jsonify(data)

@dashboard_bp.route('/dashboard/data/json/premium_roles', methods=['GET'])
@require_api_key # Add API key protection
async def get_premium_roles_json():
    data = read_json_file(PREMIUM_ROLES_FILE)
    return jsonify(data)

@dashboard_bp.route('/dashboard/data/json/previous_role_colors', methods=['GET'])
@require_api_key # Add API key protection
async def get_previous_role_colors_json():
    data = read_json_file(PREVIOUS_ROLE_COLORS_FILE)
    return jsonify(data)

@dashboard_bp.route('/dashboard/data/json/role_color_cycles', methods=['GET'])
@require_api_key # Add API key protection
async def get_role_color_cycles_json():
    data = read_json_file(ROLE_COLOR_CYCLES_FILE)
    return jsonify(data)

@dashboard_bp.route('/dashboard/data/json/tasks', methods=['GET'])
@require_api_key # Add API key protection
async def get_tasks_json():
    data = read_json_file(TASKS_FILE)
    return jsonify(data)

# --- New Bot Interaction Endpoints (under /api/bot/) ---

@dashboard_bp.route('/bot/status', methods=['GET'])
@require_api_key
def bot_status():
    """Get the bot's current status."""
    # Use global bot_instance instead of current_app.config
    if not bot_instance or not hasattr(bot_instance, 'client'):
        logger.warning("Bot instance not available. Returning error.")
        return jsonify({"error": "Bot instance not available", "mock": True}), 503
    
    return jsonify({
        "logged_in_as": str(bot_instance.client.user),
        "user_id": bot_instance.client.user.id,
        "latency": f"{bot_instance.client.latency * 1000:.2f} ms",
        "guild_count": len(bot_instance.client.guilds),
        "is_ready": bot_instance.client.is_ready()
    })

@dashboard_bp.route('/bot/guilds/<int:guild_id>', methods=['GET'])
@require_api_key
def get_guild_details(guild_id):
    """Get details for a specific guild."""
    # Use global bot_instance instead of current_app.config
    if not bot_instance or not hasattr(bot_instance, 'client'):
        logger.warning("Bot instance not available. Returning error.")
        return jsonify({"error": "Bot instance not available", "mock": True}), 503
        
    guild = bot_instance.client.get_guild(guild_id)
    if not guild:
        return jsonify({"error": f"Guild with ID {guild_id} not found or bot is not in it."}), 404
        
    return jsonify({
        "id": guild.id,
        "name": guild.name,
        "member_count": guild.member_count,
        "owner_id": guild.owner_id,
        "created_at": guild.created_at.isoformat(),
        "icon_url": str(guild.icon.url) if guild.icon else None,
        "channels": [{"id": c.id, "name": c.name, "type": str(c.type)} for c in guild.channels],
        "roles": [{"id": r.id, "name": r.name, "color": str(r.color)} for r in guild.roles]
    })

@dashboard_bp.route('/bot/users/<int:user_id>', methods=['GET'])
@require_api_key
async def get_user_details(user_id):
    """Get details for a specific user across all guilds the bot shares."""
    # Use global bot_instance instead of current_app.config
    if not bot_instance or not hasattr(bot_instance, 'client'):
        logger.warning("Bot instance not available. Returning error.")
        return jsonify({"error": "Bot instance not available", "mock": True}), 503
        
    user = bot_instance.client.get_user(user_id)
    if not user:
        # Try fetching if not in cache
        try:
            user = await bot_instance.client.fetch_user(user_id)
        except discord.NotFound:
            return jsonify({"error": f"User with ID {user_id} not found."}), 404
        except discord.HTTPException:
             return jsonify({"error": "Failed to fetch user details from Discord."}), 500
             
    guild_memberships = []
    for guild in bot_instance.client.guilds:
        member = guild.get_member(user_id)
        if member:
            guild_memberships.append({
                "guild_id": guild.id,
                "guild_name": guild.name,
                "nick": member.nick,
                "joined_at": member.joined_at.isoformat() if member.joined_at else None,
                "roles": [{"id": r.id, "name": r.name} for r in member.roles if r.name != "@everyone"]
            })
            
    return jsonify({
        "id": user.id,
        "name": user.name,
        "discriminator": user.discriminator,
        "avatar_url": str(user.avatar.url) if user.avatar else None,
        "is_bot": user.bot,
        "created_at": user.created_at.isoformat(),
        "guilds": guild_memberships
    })

@dashboard_bp.route('/bot/tasks', methods=['GET'])
@require_api_key
def list_scheduled_tasks():
    """List all currently scheduled tasks."""
    # Use global bot_instance instead of current_app.config
    if not bot_instance or not hasattr(bot_instance, 'scheduler'):
        logger.warning("Bot instance or scheduler not available. Returning error.")
        return jsonify({"error": "Bot instance or scheduler not available", "mock": True}), 503
        
    tasks = bot_instance.scheduler.get_scheduled_tasks()
    return jsonify(tasks)

@dashboard_bp.route('/bot/cogs', methods=['GET'])
@require_api_key
def list_loaded_cogs():
    """List all currently loaded cogs."""
    # Use global bot_instance instead of current_app.config
    if not bot_instance or not hasattr(bot_instance, 'client') or not hasattr(bot_instance.client, 'cogs'):
        logger.warning("Bot instance or cogs not available. Returning error.")
        return jsonify({"error": "Bot instance or cogs not available", "mock": True}), 503
        
    loaded_cogs = list(bot_instance.client.cogs.keys())
    return jsonify({"loaded_cogs": loaded_cogs})

# --- Helper Functions (Keep existing read_json_file and mock data generators) ---

# Helper function to read JSON files
def read_json_file(file_path):
    if not os.path.exists(file_path):
        logger.warning(f"JSON file not found: {file_path}")
        return {"error": f"File not found: {os.path.basename(file_path)}"}
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from {file_path}: {e}")
        return {"error": f"Invalid JSON in {os.path.basename(file_path)}"}
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}", exc_info=True)
        return {"error": f"Failed to read {os.path.basename(file_path)}"}

# Mock data generators for testing
def get_mock_data():
    return {
        "message_count": 1234,
        "user_count": 56,
        "channel_count": 7,
        "ai_interaction_count": 89,
        "daily_messages": [
            {"date": "2025-04-10", "count": 42},
            {"date": "2025-04-11", "count": 53},
            {"date": "2025-04-12", "count": 28},
            {"date": "2025-04-13", "count": 35},
            {"date": "2025-04-14", "count": 61},
            {"date": "2025-04-15", "count": 48},
            {"date": "2025-04-16", "count": 37}
        ],
        "active_users": [
            {"username": "User1", "message_count": 120},
            {"username": "User2", "message_count": 85},
            {"username": "User3", "message_count": 72}
        ]
    }

def get_mock_message_data():
    return {
        "daily_messages": [
            {"date": "2025-04-10", "count": 42},
            {"date": "2025-04-11", "count": 53},
            {"date": "2025-04-12", "count": 28},
            {"date": "2025-04-13", "count": 35},
            {"date": "2025-04-14", "count": 61},
            {"date": "2025-04-15", "count": 48},
            {"date": "2025-04-16", "count": 37}
        ],
        "messages_by_channel": [
            {"channel_name": "general", "count": 423},
            {"channel_name": "random", "count": 215},
            {"channel_name": "bot-commands", "count": 178}
        ],
        "hourly_activity": [
            {"hour": 0, "weekday": "Monday", "count": 12},
            {"hour": 1, "weekday": "Monday", "count": 5},
            {"hour": 2, "weekday": "Monday", "count": 3}
            # ... more data points
        ]
    }

def get_mock_user_data():
    return {
        "active_users": [
            {"username": "User1", "message_count": 120},
            {"username": "User2", "message_count": 85},
            {"username": "User3", "message_count": 72},
            {"username": "User4", "message_count": 65},
            {"username": "User5", "message_count": 58}
        ],
        "user_roles": [
            {"role": "Admin", "count": 3},
            {"role": "Moderator", "count": 8},
            {"role": "Member", "count": 45}
        ],
        "user_growth": [
            {"date": "2025-03-18", "count": 32},
            {"date": "2025-03-25", "count": 37},
            {"date": "2025-04-01", "count": 42},
            {"date": "2025-04-08", "count": 48},
            {"date": "2025-04-15", "count": 56}
        ]
    }

def get_mock_ai_data():
    return {
        "ai_models": [
            {"model": "GPT-4", "count": 150},
            {"model": "Claude 3 Opus", "count": 120},
            {"model": "Gemini Pro", "count": 95}
        ],
        "ai_daily": [
            {"date": "2025-04-10", "count": 12},
            {"date": "2025-04-11", "count": 18},
            {"date": "2025-04-12", "count": 9},
            {"date": "2025-04-13", "count": 14},
            {"date": "2025-04-14", "count": 22},
            {"date": "2025-04-15", "count": 15}
        ],
        "ai_users": [
            {"username": "User1", "count": 42},
            {"username": "User2", "count": 37},
            {"username": "User3", "count": 25},
            {"username": "User4", "count": 18},
            {"username": "User5", "count": 12}
        ]
    }

def get_mock_guilds():
    return [
        {
            "id": "1234567890123456789",
            "name": "Test Server 1",
            "icon": None,
            "member_count": 128
        },
        {
            "id": "9876543210987654321",
            "name": "Test Server 2",
            "icon": None,
            "member_count": 56
        }
    ]