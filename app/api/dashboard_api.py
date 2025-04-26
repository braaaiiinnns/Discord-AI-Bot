"""
API routes for dashboard functionality.
"""

import logging
import os
import time
from datetime import datetime, timedelta
from quart import Blueprint, jsonify, request
from .middleware import require_auth

# Set up logger
logger = logging.getLogger('discord_bot.api.dashboard')

# Global variables
bot_instance_ref = None
data_service = None

# Create Blueprint
dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/api')

async def initialize(bot):
    """Initialize the dashboard API with a reference to the bot"""
    global bot_instance_ref, data_service
    bot_instance_ref = bot
    
    if hasattr(bot, 'message_monitor') and bot.message_monitor:
        if hasattr(bot.message_monitor, 'database'):
            data_service = bot.message_monitor.database
        elif hasattr(bot.message_monitor, 'get_database'):
            data_service = bot.message_monitor.get_database()
            
    logger.info("Dashboard API initialized")

@dashboard_bp.route('/health')
async def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.utcnow().isoformat()
    })

@dashboard_bp.route('/dashboard/summary')
@require_auth(endpoint_name='dashboard_summary')  # Enhanced with endpoint name for better logging
async def get_dashboard_summary():
    """Get summary data for the dashboard"""
    # Extract optional guild_id parameter
    guild_id = request.args.get('guild_id')
    
    # Log request details for diagnostics
    api_key = getattr(request, 'api_key', 'None')
    user = getattr(request, 'user', None)
    
    # Enhanced logging for authentication debugging
    logger.info(f"Dashboard summary requested for guild_id={guild_id}")
    logger.info(f"Request authenticated with API key: {api_key[:5] + '...' if api_key and api_key != 'None' else 'None'}")
    if user:
        logger.info(f"Authenticated user: {user.get('username')} (ID: {user.get('id')})")
        logger.info(f"User access status: {user.get('access_status', 'unknown')}")
        logger.info(f"Is admin: {user.get('is_admin', False)}")
    else:
        logger.warning(f"No authenticated user for dashboard/summary request")
        if api_key and api_key != 'None':
            logger.warning(f"API key validation succeeded but no user was found - possible system key")
    
    try:
        # Get data from the database
        if data_service:
            # Pass guild_id as a dictionary with 'guild_id' key
            filter_criteria = {'guild_id': guild_id} if guild_id else None
            
            # Log the data request
            logger.info(f"Fetching dashboard summary with filter: {filter_criteria}")
            
            summary = await data_service.get_dashboard_summary(filter_criteria)
            logger.info(f"Successfully retrieved dashboard summary: {summary.keys() if summary else 'None'}")
            return jsonify(summary)
        else:
            # Fallback to mock data if data service is not available
            logger.warning("Data service not available, using mock data")
            mock_data = get_mock_summary_data()
            logger.info(f"Using mock data: {mock_data}")
            return jsonify(mock_data)
    except Exception as e:
        logger.error(f"Error getting dashboard summary: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to retrieve dashboard data"}), 500

@dashboard_bp.route('/bot/status')
@require_auth(endpoint_name='bot_status')  # Enhanced with endpoint name for better logging
async def get_bot_status():
    """Get the status of the Discord bot"""
    try:
        if not bot_instance_ref:
            return jsonify({
                "status": "unknown",
                "error": "Bot reference not available"
            }), 404
            
        # First check if the bot instance exists and has the client attribute
        if not hasattr(bot_instance_ref, 'client'):
            logger.error("Bot instance does not have a client attribute")
            return jsonify({"error": "Bot client not available"}), 500
            
        # Access attributes through the client
        client = bot_instance_ref.client
        
        # Now we can safely check client methods
        return jsonify({
            "status": "online" if client.is_ready() else "connecting",
            "is_ready": client.is_ready(),
            "logged_in_as": str(client.user) if client.user else None,
            "uptime": get_bot_uptime(),
            "latency": client.latency,
            "guild_count": len(client.guilds) if hasattr(client, 'guilds') else 0,
            "shard_count": client.shard_count if hasattr(client, 'shard_count') else 1
        })
    except Exception as e:
        logger.error(f"Error getting bot status: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to retrieve bot status"}), 500

@dashboard_bp.route('/bot/guilds')
@require_auth(endpoint_name='bot_guilds')  # Enhanced with endpoint name for better logging
async def get_bot_guilds():
    """Get a list of guilds (servers) the bot is a member of"""
    try:
        if not bot_instance_ref:
            return jsonify({"error": "Bot reference not available"}), 404
            
        # Check if the bot instance has a client attribute
        if not hasattr(bot_instance_ref, 'client'):
            logger.error("Bot instance does not have a client attribute")
            return jsonify({"error": "Bot client not available"}), 500
            
        # Access guilds through the client attribute
        client = bot_instance_ref.client
        
        guilds = []
        for guild in client.guilds:
            guilds.append({
                "id": str(guild.id),
                "name": guild.name,
                "member_count": guild.member_count if hasattr(guild, 'member_count') else 0,
                "icon": guild.icon.url if guild.icon else None
            })
            
        return jsonify(guilds)
    except Exception as e:
        logger.error(f"Error getting bot guilds: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to retrieve guild list"}), 500

def get_bot_uptime():
    """Get the bot's uptime as a string"""
    if not bot_instance_ref or not hasattr(bot_instance_ref, 'client'):
        return "Unknown"
        
    client = bot_instance_ref.client
    
    # Check if the client has a start_time attribute
    # In some Discord.py bots, the start time might be stored in different places
    if hasattr(client, 'start_time'):
        start_time = client.start_time
    elif hasattr(bot_instance_ref, 'start_time'):
        start_time = bot_instance_ref.start_time
    else:
        return "Unknown"
    
    uptime = datetime.utcnow() - start_time
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    
    return " ".join(parts)

def get_mock_summary_data():
    """Get mock data for dashboard summary"""
    return {
        "message_count": 12345,
        "user_count": 678,
        "ai_interaction_count": 910,
        "channel_count": 34
    }