"""
Simple data service for API access to the database.
Provides basic functionality without dashboard-specific components.
"""

import logging
import sqlite3
import json
from datetime import datetime, timedelta
from utils.logger import setup_logger
import asyncio

# Set up logger
logger = setup_logger('discord_bot.api.data_service')

class APIDataService:
    """Data service for API endpoints to access database content"""
    
    def __init__(self, db_connection):
        """
        Initialize the data service with a database connection.
        
        Args:
            db_connection: The database connection to use
        """
        self.db = db_connection
        self.connection_timeout = 10  # Default timeout in seconds
        self.max_retries = 3
        self.query_timeout = 30  # Default query timeout in seconds
        self.statement_cache = {}  # Cache for prepared statements
        logger.info("API data service initialized with enhanced connection handling")

    async def get_dashboard_summary(self, filter_criteria=None):
        """
        Get the summary data for the dashboard.
        
        Args:
            filter_criteria: Optional filter criteria to apply.
        
        Returns:
            A dictionary with the dashboard summary data.
        """
        try:
            # Start with basic WHERE clause for time filtering
            where_clause = ""
            params = []
            
            if filter_criteria and 'time_range' in filter_criteria:
                if filter_criteria['time_range'] == 'day':
                    where_clause = " WHERE timestamp > datetime('now', '-1 day')"
                elif filter_criteria['time_range'] == 'week':
                    where_clause = " WHERE timestamp > datetime('now', '-7 day')"
                elif filter_criteria['time_range'] == 'month':
                    where_clause = " WHERE timestamp > datetime('now', '-30 day')"
                    
            # Additional filters
            if filter_criteria:
                if 'guild_id' in filter_criteria and filter_criteria['guild_id']:
                    if where_clause:
                        where_clause += " AND guild_id = ?"
                    else:
                        where_clause = " WHERE guild_id = ?"
                    params.append(filter_criteria['guild_id'])
                
                if 'channel_id' in filter_criteria and filter_criteria['channel_id']:
                    if where_clause:
                        where_clause += " AND channel_id = ?"
                    else:
                        where_clause = " WHERE channel_id = ?"
                    params.append(filter_criteria['channel_id'])
                    
                if 'user_id' in filter_criteria and filter_criteria['user_id']:
                    if where_clause:
                        where_clause += " AND user_id = ?"
                    else:
                        where_clause = " WHERE user_id = ?"
                    params.append(filter_criteria['user_id'])
            
            # Query 1: Combined stats query (reduces number of DB calls)
            stats_sql = f"""
                SELECT 
                    COUNT(*) as message_count,
                    COUNT(DISTINCT user_id) as user_count,
                    COUNT(DISTINCT channel_id) as channel_count,
                    COUNT(DISTINCT guild_id) as guild_count,
                    MIN(timestamp) as earliest_message,
                    MAX(timestamp) as latest_message
                FROM messages
                {where_clause}
            """
            
            stats_cursor = await self.execute_query(stats_sql, params)
            if not stats_cursor:
                return {"error": "Failed to get basic statistics"}
                
            stats_row = stats_cursor.fetchone()
            message_count = stats_row[0]
            user_count = stats_row[1]
            channel_count = stats_row[2]
            guild_count = stats_row[3]
            earliest_message = stats_row[4]
            latest_message = stats_row[5]
            
            # Query 2: Get AI interactions count
            ai_count_sql = f"""
                SELECT COUNT(*) 
                FROM ai_interactions ai
                JOIN messages m ON ai.message_id = m.id
                {where_clause.replace('FROM messages', '')}
            """
            
            # Handle empty where clause
            if not where_clause:
                ai_count_sql = "SELECT COUNT(*) FROM ai_interactions"
                params_ai = []
            else:
                params_ai = params
            
            ai_cursor = await self.execute_query(ai_count_sql, params_ai)
            if not ai_cursor:
                ai_count = 0
            else:
                ai_count = ai_cursor.fetchone()[0]
            
            # Query 3: Message activity over time (last 30 days)
            time_sql = f"""
                SELECT 
                    strftime('%Y-%m-%d', timestamp) as date,
                    COUNT(*) as count
                FROM messages
                {where_clause}
                GROUP BY date
                ORDER BY date DESC
                LIMIT 30
            """
            
            time_cursor = await self.execute_query(time_sql, params)
            if not time_cursor:
                time_data = []
            else:
                time_data = time_cursor.fetchall()
            
            # Query 4: Top users
            top_users_sql = f"""
                SELECT 
                    user_id,
                    username,
                    COUNT(*) as message_count
                FROM messages
                {where_clause}
                GROUP BY user_id
                ORDER BY message_count DESC
                LIMIT 5
            """
            
            top_users_cursor = await self.execute_query(top_users_sql, params)
            if not top_users_cursor:
                top_users = []
            else:
                top_users_rows = top_users_cursor.fetchall()
                top_users = [
                    {"user_id": row[0], "username": row[1], "message_count": row[2]}
                    for row in top_users_rows
                ]
            
            # Query 5: Top channels
            top_channels_sql = f"""
                SELECT 
                    channel_id,
                    channel_name,
                    COUNT(*) as message_count
                FROM messages
                {where_clause}
                GROUP BY channel_id
                ORDER BY message_count DESC
                LIMIT 5
            """
            
            top_channels_cursor = await self.execute_query(top_channels_sql, params)
            if not top_channels_cursor:
                top_channels = []
            else:
                top_channels_rows = top_channels_cursor.fetchall()
                top_channels = [
                    {"channel_id": row[0], "channel_name": row[1], "message_count": row[2]}
                    for row in top_channels_rows
                ]
            
            # Return the comprehensive dashboard summary data
            return {
                "message_count": message_count,
                "user_count": user_count,
                "channel_count": channel_count,
                "guild_count": guild_count,
                "ai_interaction_count": ai_count,
                "time_range": filter_criteria.get('time_range', 'all') if filter_criteria else 'all',
                "earliest_message": earliest_message,
                "latest_message": latest_message,
                "messages_per_day": round(message_count / 30, 1) if message_count > 0 else 0,
                "time_data": [{"date": date, "count": count} for date, count in time_data],
                "top_users": top_users,
                "top_channels": top_channels
            }
            
        except Exception as e:
            logger.error(f"Error getting dashboard summary: {e}", exc_info=True)
            return {"error": str(e)}

    async def get_message_stats(self, filter_criteria=None, days=30):
        """Get comprehensive message statistics with filtering options"""
        try:
            # Start with base query for daily message counts
            base_sql = """
                SELECT 
                    DATE(timestamp) as date,
                    COUNT(*) as message_count
                FROM messages 
            """

            # Build WHERE clause based on filter criteria
            where_conditions = []
            params = []
            
            # Start date filter (always included)
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            where_conditions.append("timestamp >= ?")
            params.append(start_date)
            
            # Optional end date filter
            if filter_criteria and 'end_date' in filter_criteria and filter_criteria['end_date']:
                where_conditions.append("timestamp <= ?")
                params.append(filter_criteria['end_date'])
            
            # Add other filter conditions
            if filter_criteria:
                if 'guild_id' in filter_criteria and filter_criteria['guild_id']:
                    where_conditions.append("guild_id = ?")
                    params.append(filter_criteria['guild_id'])
                
                if 'channel_id' in filter_criteria and filter_criteria['channel_id']:
                    where_conditions.append("channel_id = ?")
                    params.append(filter_criteria['channel_id'])
                
                if 'user_id' in filter_criteria and filter_criteria['user_id']:
                    where_conditions.append("user_id = ?")
                    params.append(filter_criteria['user_id'])
            
            # Construct the WHERE clause
            where_clause = " WHERE " + " AND ".join(where_conditions) if where_conditions else ""
            
            # Query 1: Daily message counts
            daily_sql = base_sql + where_clause + """
                GROUP BY date
                ORDER BY date
            """
            
            daily_cursor = await self.execute_query(daily_sql, params)
            if not daily_cursor:
                return {"error": "Failed to get daily message counts"}
            
            daily_counts = [{"date": row[0], "count": row[1]} for row in daily_cursor.fetchall()]
            
            # Query 2: Channel statistics
            channel_sql = f"""
                SELECT 
                    channel_id, 
                    channel_name,
                    COUNT(*) as message_count
                FROM messages
                {where_clause}
                GROUP BY channel_id
                ORDER BY message_count DESC
                LIMIT 10
            """
            
            channel_cursor = await self.execute_query(channel_sql, params)
            if not channel_cursor:
                return {"error": "Failed to get channel statistics"}
            
            channel_stats = [
                {
                    "channel_id": row[0],
                    "channel_name": row[1],
                    "message_count": row[2]
                } 
                for row in channel_cursor.fetchall()
            ]
            
            # Query 3: Hourly activity distribution
            hourly_sql = f"""
                SELECT 
                    strftime('%H', timestamp) as hour,
                    COUNT(*) as count
                FROM messages
                {where_clause}
                GROUP BY hour
                ORDER BY hour
            """
            
            hourly_cursor = await self.execute_query(hourly_sql, params)
            if not hourly_cursor:
                return {"error": "Failed to get hourly distribution"}
            
            hourly_distribution = [{"hour": int(row[0]), "count": row[1]} for row in hourly_cursor.fetchall()]
            
            # Query 4: Weekday distribution
            weekday_sql = f"""
                SELECT 
                    strftime('%w', timestamp) as weekday,
                    COUNT(*) as count
                FROM messages
                {where_clause}
                GROUP BY weekday
                ORDER BY weekday
            """
            
            weekday_cursor = await self.execute_query(weekday_sql, params)
            if not weekday_cursor:
                return {"error": "Failed to get weekday distribution"}
            
            weekday_distribution = [{"weekday": int(row[0]), "count": row[1]} for row in weekday_cursor.fetchall()]
            
            # Query 5: Message length distribution
            length_sql = f"""
                SELECT 
                    CASE 
                        WHEN LENGTH(content) < 20 THEN 'Very Short'
                        WHEN LENGTH(content) < 100 THEN 'Short'
                        WHEN LENGTH(content) < 500 THEN 'Medium'
                        ELSE 'Long'
                    END as length_category,
                    COUNT(*) as count
                FROM messages
                {where_clause}
                GROUP BY length_category
                ORDER BY 
                    CASE length_category
                        WHEN 'Very Short' THEN 1
                        WHEN 'Short' THEN 2
                        WHEN 'Medium' THEN 3
                        WHEN 'Long' THEN 4
                    END
            """
            
            length_cursor = await self.execute_query(length_sql, params)
            if not length_cursor:
                return {"error": "Failed to get message length distribution"}
            
            length_distribution = [{"category": row[0], "count": row[1]} for row in length_cursor.fetchall()]
            
            # Query 6: Total messages and unique users
            totals_sql = f"""
                SELECT 
                    COUNT(*) as total_messages,
                    COUNT(DISTINCT user_id) as unique_users
                FROM messages
                {where_clause}
            """
            
            totals_cursor = await self.execute_query(totals_sql, params)
            if not totals_cursor:
                return {"error": "Failed to get total statistics"}
            
            totals_row = totals_cursor.fetchone()
            total_messages = totals_row[0]
            unique_users = totals_row[1]
            
            # Query 7: AI interaction stats
            ai_stats_sql = f"""
                SELECT 
                    COUNT(*) as ai_interactions,
                    COUNT(DISTINCT message_id) as unique_messages
                FROM ai_interactions ai
                JOIN messages m ON ai.message_id = m.id
                {where_clause.replace('FROM messages', 'FROM ai_interactions ai JOIN messages m ON ai.message_id = m.id')}
            """
            
            # Adjusted SQL if there's no where clause
            if not where_clause:
                ai_stats_sql = """
                    SELECT 
                        COUNT(*) as ai_interactions,
                        COUNT(DISTINCT message_id) as unique_messages
                    FROM ai_interactions ai
                    JOIN messages m ON ai.message_id = m.id
                    WHERE timestamp >= ?
                """
            
            ai_stats_cursor = await self.execute_query(ai_stats_sql, params)
            if not ai_stats_cursor:
                ai_interactions = 0
                ai_messages = 0
            else:
                ai_row = ai_stats_cursor.fetchone()
                ai_interactions = ai_row[0]
                ai_messages = ai_row[1]
            
            # Return comprehensive statistics
            return {
                "total_stats": {
                    "total_messages": total_messages,
                    "unique_users": unique_users,
                    "messages_per_day": round(total_messages / days, 1) if days > 0 else 0
                },
                "ai_stats": {
                    "ai_interactions": ai_interactions,
                    "ai_message_percentage": round(ai_messages / total_messages * 100, 1) if total_messages > 0 else 0
                },
                "daily_counts": daily_counts,
                "channel_stats": channel_stats,
                "hourly_distribution": hourly_distribution,
                "weekday_distribution": weekday_distribution,
                "length_distribution": length_distribution
            }
            
        except Exception as e:
            logger.error(f"Error getting message stats: {e}", exc_info=True)
            return {"error": str(e)}

    async def get_user_stats(self, filter_criteria=None, limit=10):
        """Get statistics about top users"""
        try:
            # Build WHERE clause based on filter criteria
            where_conditions = []
            params = []
            
            # Add filters
            if filter_criteria:
                if 'guild_id' in filter_criteria and filter_criteria['guild_id']:
                    where_conditions.append("guild_id = ?")
                    params.append(filter_criteria['guild_id'])
                
                if 'channel_id' in filter_criteria and filter_criteria['channel_id']:
                    where_conditions.append("channel_id = ?")
                    params.append(filter_criteria['channel_id'])
                    
                if 'start_date' in filter_criteria and filter_criteria['start_date']:
                    where_conditions.append("timestamp >= ?")
                    params.append(filter_criteria['start_date'])
                    
                if 'end_date' in filter_criteria and filter_criteria['end_date']:
                    where_conditions.append("timestamp <= ?")
                    params.append(filter_criteria['end_date'])
            
            # Construct the WHERE clause
            where_clause = " WHERE " + " AND ".join(where_conditions) if where_conditions else ""
            
            # Add limit parameter
            params.append(limit)
            
            # Query 1: Get top users by message count
            user_stats_sql = f"""
                SELECT 
                    user_id,
                    username,
                    COUNT(*) as message_count,
                    AVG(LENGTH(content)) as avg_length,
                    MAX(timestamp) as last_active,
                    MIN(timestamp) as first_active
                FROM messages
                {where_clause}
                GROUP BY user_id
                ORDER BY message_count DESC
                LIMIT ?
            """
            
            user_cursor = await self.execute_query(user_stats_sql, params)
            if not user_cursor:
                return {"error": "Failed to get user statistics"}
                
            users = user_cursor.fetchall()
            
            # Query 2: Get active days count for each user
            user_days = {}
            for user_id, *_ in users:
                # Clone the where conditions and params
                user_where_conditions = where_conditions.copy()
                user_params = params[:-1].copy()  # Exclude the limit parameter
                
                # Add user filter
                user_where_conditions.append("user_id = ?")
                user_params.append(user_id)
                
                # Build WHERE clause
                user_where_clause = " WHERE " + " AND ".join(user_where_conditions) if user_where_conditions else " WHERE user_id = ?"
                if not where_conditions:
                    user_params = [user_id]
                
                days_sql = f"""
                    SELECT COUNT(DISTINCT DATE(timestamp)) as active_days
                    FROM messages
                    {user_where_clause}
                """
                
                days_cursor = await self.execute_query(days_sql, user_params)
                if days_cursor:
                    active_days = days_cursor.fetchone()[0]
                    user_days[user_id] = active_days
            
            # Query 3: Get message trends for top 5 users
            user_trends = []
            for user_id, username, *_ in users[:5]:  # Only get trends for top 5 users
                # Build user-specific WHERE clause
                trend_where_conditions = ["user_id = ?"]
                trend_params = [user_id]
                
                # Add other filters
                if filter_criteria:
                    if 'guild_id' in filter_criteria and filter_criteria['guild_id']:
                        trend_where_conditions.append("guild_id = ?")
                        trend_params.append(filter_criteria['guild_id'])
                    
                    if 'channel_id' in filter_criteria and filter_criteria['channel_id']:
                        trend_where_conditions.append("channel_id = ?")
                        trend_params.append(filter_criteria['channel_id'])
                    
                    if 'start_date' in filter_criteria and filter_criteria['start_date']:
                        trend_where_conditions.append("timestamp >= ?")
                        trend_params.append(filter_criteria['start_date'])
                        
                    if 'end_date' in filter_criteria and filter_criteria['end_date']:
                        trend_where_conditions.append("timestamp <= ?")
                        trend_params.append(filter_criteria['end_date'])
                
                trend_where_clause = " WHERE " + " AND ".join(trend_where_conditions)
                
                trend_sql = f"""
                    SELECT 
                        DATE(timestamp) as date,
                        COUNT(*) as count
                    FROM messages
                    {trend_where_clause}
                    GROUP BY date
                    ORDER BY date
                    LIMIT 30
                """
                
                trend_cursor = await self.execute_query(trend_sql, trend_params)
                if trend_cursor:
                    trend_data = trend_cursor.fetchall()
                    user_trends.append({
                        "user_id": user_id,
                        "username": username,
                        "trend": [{"date": date, "count": count} for date, count in trend_data]
                    })
            
            # Query 4: Get top channels for each user (top 5 users only)
            user_channels = {}
            for user_id, username, *_ in users[:5]:
                channels_where_conditions = ["user_id = ?"]
                channels_params = [user_id]
                
                # Add other filters (except channel_id)
                if filter_criteria:
                    if 'guild_id' in filter_criteria and filter_criteria['guild_id']:
                        channels_where_conditions.append("guild_id = ?")
                        channels_params.append(filter_criteria['guild_id'])
                    
                    if 'start_date' in filter_criteria and filter_criteria['start_date']:
                        channels_where_conditions.append("timestamp >= ?")
                        channels_params.append(filter_criteria['start_date'])
                        
                    if 'end_date' in filter_criteria and filter_criteria['end_date']:
                        channels_where_conditions.append("timestamp <= ?")
                        channels_params.append(filter_criteria['end_date'])
                
                channels_where_clause = " WHERE " + " AND ".join(channels_where_conditions)
                
                channels_sql = f"""
                    SELECT 
                        channel_id,
                        channel_name,
                        COUNT(*) as message_count
                    FROM messages
                    {channels_where_clause}
                    GROUP BY channel_id
                    ORDER BY message_count DESC
                    LIMIT 3
                """
                
                channels_cursor = await self.execute_query(channels_sql, channels_params)
                if channels_cursor:
                    channel_data = channels_cursor.fetchall()
                    user_channels[user_id] = [
                        {"channel_id": row[0], "channel_name": row[1], "count": row[2]}
                        for row in channel_data
                    ]
            
            # Format and return results
            return {
                "top_users": [
                    {
                        "user_id": user_id,
                        "username": username,
                        "message_count": message_count,
                        "avg_length": round(avg_length, 1) if avg_length else 0,
                        "last_active": last_active,
                        "first_active": first_seen,
                        "active_days": user_days.get(user_id, 0),
                        "top_channels": user_channels.get(user_id, []) if user_id in user_channels else []
                    }
                    for user_id, username, message_count, avg_length, last_active, first_seen in users
                ],
                "user_trends": user_trends
            }
            
        except Exception as e:
            logger.error(f"Error getting user stats: {e}", exc_info=True)
            return {"error": str(e)}

    async def get_ai_stats(self, filter_criteria=None, days=30):
        """Get AI interaction statistics"""
        result = {
            "ai_models": [],
            "ai_daily": [],
            "ai_users": []
        }
        
        try:
            # Check if we have a separate AI database
            ai_db = self.get_ai_db()
            if ai_db:
                # Use the AI database connection if available
                logger.info("Using dedicated AI interactions database connection")
                # Check if ai_db is a UnifiedDatabase instance with async cursor
                if hasattr(ai_db, 'cursor') and asyncio.iscoroutinefunction(ai_db.cursor):
                    cursor = await ai_db.cursor()
                else:
                    cursor = ai_db.cursor()
            elif not ai_db:
                # Fall back to the main database connection
                logger.warning("AI database connection not found, using main database connection for AI stats")
                cursor = await self.db.cursor()
            
            # First, check the table schema to determine what columns we have
            try:
                cursor.execute("PRAGMA table_info(ai_interactions)")
                columns_info = cursor.fetchall()
                column_names = [col[1] for col in columns_info]
                logger.debug(f"AI interactions table columns: {column_names}")
                
                has_user_name = 'user_name' in column_names
            except Exception as e:
                logger.error(f"Error checking AI interactions table schema: {e}")
                has_user_name = False
            
            # Add WHERE clause if filter criteria provided
            where_clause = ""
            params = []
            if filter_criteria and 'guild_id' in filter_criteria and filter_criteria['guild_id']:
                where_clause = "WHERE guild_id = ?"
                params = [filter_criteria['guild_id']]
            
            # Get AI usage by model
            if where_clause:
                models_query = f"""
                    SELECT model, COUNT(*) as count
                    FROM ai_interactions
                    {where_clause}
                    GROUP BY model
                    ORDER BY count DESC
                """
                cursor.execute(models_query, params)
            else:
                models_query = """
                    SELECT model, COUNT(*) as count
                    FROM ai_interactions
                    GROUP BY model
                    ORDER BY count DESC
                """
                cursor.execute(models_query)
            
            result["ai_models"] = [{"model": row[0], "count": row[1]} for row in cursor.fetchall()]
            
            # Get daily AI usage
            days_ago = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            
            if where_clause:
                daily_query = f"""
                    SELECT DATE(timestamp) as date, COUNT(*) as count
                    FROM ai_interactions
                    {where_clause} AND DATE(timestamp) >= ?
                    GROUP BY date
                    ORDER BY date
                """
                cursor.execute(daily_query, params + [days_ago])
            else:
                daily_query = """
                    SELECT DATE(timestamp) as date, COUNT(*) as count
                    FROM ai_interactions
                    WHERE DATE(timestamp) >= ?
                    GROUP BY date
                    ORDER BY date
                """
                cursor.execute(daily_query, [days_ago])
            
            result["ai_daily"] = [{"date": row[0], "count": row[1]} for row in cursor.fetchall()]
            
            # Get top AI users - adjust query based on schema
            if has_user_name:
                # Use user_name if it exists
                user_column = "user_name"
            else:
                # Fall back to user_id if user_name doesn't exist
                user_column = "user_id"
                
            if where_clause:
                users_query = f"""
                    SELECT {user_column}, COUNT(*) as count
                    FROM ai_interactions
                    {where_clause}
                    GROUP BY {user_column}
                    ORDER BY count DESC
                    LIMIT 5
                """
                cursor.execute(users_query, params)
            else:
                users_query = f"""
                    SELECT {user_column}, COUNT(*) as count
                    FROM ai_interactions
                    GROUP BY {user_column}
                    ORDER BY count DESC
                    LIMIT 5
                """
                cursor.execute(users_query)
            
            result["ai_users"] = [{"username": row[0], "count": row[1]} for row in cursor.fetchall()]
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting AI stats: {e}", exc_info=True)
            return result

    async def get_all_messages(self):
        """Get all messages from the database."""
        try:
            cursor = await self.db.cursor()
            cursor.execute("SELECT * FROM messages ORDER BY timestamp DESC LIMIT 1000")
            
            # Check if we got any results
            if cursor.description is None:
                logger.error("No data returned from messages query, table may not exist")
                return []
                
            columns = [column[0] for column in cursor.description]
            messages = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            logger.info(f"Retrieved {len(messages)} messages")
            return messages
        except Exception as e:
            logger.error(f"Error getting messages: {e}", exc_info=True)
            return []

    async def get_all_files(self):
        """Get all files from the database"""
        try:
            cursor = await self.db.cursor()
            cursor.execute("SELECT * FROM files ORDER BY timestamp DESC LIMIT 1000")
            columns = [column[0] for column in cursor.description]
            files = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return files
        except Exception as e:
            logger.error(f"Error getting files: {e}")
            return []

    async def get_all_reactions(self):
        """Get all reactions from the database."""
        try:
            cursor = await self.db.cursor()
            cursor.execute("SELECT * FROM reactions ORDER BY timestamp DESC LIMIT 1000")
            columns = [column[0] for column in cursor.description]
            reactions = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return reactions
        except Exception as e:
            logger.error(f"Error getting reactions: {e}")
            return []

    async def get_all_message_edits(self):
        """Get all message edits from the database"""
        try:
            cursor = await self.db.cursor()
            
            # First check if the message_edits table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='message_edits'")
            if cursor.fetchone() is None:
                logger.warning("message_edits table does not exist in database")
                return []
                
            # Check if timestamp or edit_timestamp column exists by getting the schema
            cursor.execute("PRAGMA table_info(message_edits)")
            columns_info = cursor.fetchall()
            column_names = [col[1] for col in columns_info]
            
            # Determine the timestamp column name
            timestamp_col = None
            if 'timestamp' in column_names:
                timestamp_col = 'timestamp'
            elif 'edit_timestamp' in column_names:
                timestamp_col = 'edit_timestamp'
                
            # Use the correct ordering column
            if timestamp_col:
                query = f"SELECT * FROM message_edits ORDER BY {timestamp_col} DESC LIMIT 1000"
            else:
                logger.warning("No timestamp column found in message_edits, using default ordering")
                query = "SELECT * FROM message_edits LIMIT 1000"
                
            cursor.execute(query)
            columns = [column[0] for column in cursor.description]
            edits = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return edits
        except Exception as e:
            logger.error(f"Error getting message edits: {e}")
            return []
            
    async def get_all_channels(self):
        """Get all channels from the database"""
        try:
            cursor = await self.db.cursor()
            
            # First check if the channels table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='channels'")
            if cursor.fetchone() is None:
                logger.warning("channels table does not exist in database")
                return []
                
            cursor.execute("SELECT * FROM channels")
            columns = [column[0] for column in cursor.description]
            channels = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return channels
        except Exception as e:
            logger.error(f"Error getting channels: {e}")
            return []

    async def get_all_ai_interactions(self):
        """Get all AI interactions from the database"""
        try:
            # Check if we have a separate AI database
            ai_db = self.get_ai_db()
            if ai_db:
                # Use the AI database connection if available
                logger.info("Using dedicated AI interactions database connection")
                # Check if ai_db is a UnifiedDatabase instance with async cursor
                if hasattr(ai_db, 'cursor') and asyncio.iscoroutinefunction(ai_db.cursor):
                    cursor = await ai_db.cursor()
                else:
                    cursor = ai_db.cursor()
            else:
                # Fall back to the main database connection
                logger.warning("AI database connection not found, using main database connection")
                cursor = await self.db.cursor()
            
            cursor.execute("SELECT * FROM ai_interactions ORDER BY timestamp DESC LIMIT 1000")
            
            # Check if we got any results
            if cursor.description is None:
                logger.error("No data returned from AI interactions query, table may not exist")
                return []
                
            columns = [column[0] for column in cursor.description]
            ai_interactions = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            logger.info(f"Retrieved {len(ai_interactions)} AI interactions")
            return ai_interactions
        except Exception as e:
            logger.error(f"Error getting AI interactions: {e}", exc_info=True)
            return []

    def get_ai_db(self):
        """Get the AI database connection if available"""
        ai_db = None
        
        # First, try to access the AI database directly from the bot's message monitor
        if hasattr(self.db, 'get_ai_database'):
            ai_db = self.db.get_ai_database()
        
        # If that doesn't work, try to see if there's an ai_db attribute
        if not ai_db and hasattr(self.db, 'ai_db'):
            ai_db = self.db.ai_db
            
        return ai_db

    async def test_connection(self):
        """Test the database connection with a simple query"""
        retries = 0
        while retries <= self.max_retries:
            try:
                if not self.db:
                    logger.warning("No database connection to test")
                    return False
                    
                logger.info(f"Testing database connection (attempt {retries+1}/{self.max_retries+1})...")
                cursor = await self.db.cursor()
                
                # Try a very simple query to test the connection
                try:
                    # Set timeout if supported
                    if hasattr(self.db, 'timeout'):
                        original_timeout = self.db.timeout
                        self.db.timeout = self.connection_timeout
                        
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    
                    # Restore original timeout if changed
                    if hasattr(self.db, 'timeout'):
                        self.db.timeout = original_timeout
                        
                    if result and result[0] == 1:
                        logger.info("Database connection test successful")
                        return True
                    else:
                        logger.warning("Database connection test failed - unexpected result")
                        retries += 1
                        if retries <= self.max_retries:
                            await asyncio.sleep(1)  # Wait before retry
                        continue
                except Exception as e:
                    logger.error(f"Database query error during connection test: {e}", exc_info=True)
                    retries += 1
                    if retries <= self.max_retries:
                        await asyncio.sleep(1)  # Wait before retry
                    continue
                    
            except Exception as e:
                logger.error(f"Error testing database connection: {e}", exc_info=True)
                retries += 1
                if retries <= self.max_retries:
                    await asyncio.sleep(1)  # Wait before retry
                continue
                
        return False  # Return False after all retries have failed
        
    async def execute_query(self, query, params=None, timeout=None):
        """
        Execute a database query with proper error handling and timeout
        
        Args:
            query: SQL query string
            params: Query parameters (optional)
            timeout: Custom timeout in seconds (optional)
            
        Returns:
            Cursor object on success, None on failure
        """
        if not self.db:
            logger.warning("No database connection for query execution")
            return None
            
        query_timeout = timeout or self.query_timeout
        
        try:
            # Set timeout if supported
            if hasattr(self.db, 'timeout'):
                original_timeout = self.db.timeout
                self.db.timeout = query_timeout
                
            cursor = await self.db.cursor()
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
                
            # Restore original timeout if changed
            if hasattr(self.db, 'timeout'):
                self.db.timeout = original_timeout
                
            return cursor
            
        except Exception as e:
            logger.error(f"Error executing query: {e}", exc_info=True)
            return None

    async def get_message_history(self, filter_criteria=None, limit=100, offset=0):
        """Get message history with filtering options"""
        try:
            # Start with basic query
            query = """
                SELECT 
                    m.id, m.user_id, m.username, m.guild_id, m.guild_name, 
                    m.channel_id, m.channel_name, m.content, m.timestamp,
                    COALESCE(ai.response, '') as ai_response,
                    COALESCE(ai.model, '') as ai_model,
                    COALESCE(ai.timestamp, '') as ai_timestamp
                FROM messages m
                LEFT JOIN ai_interactions ai ON m.id = ai.message_id
            """
            
            # Initialize parameters list
            params = []
            
            # Build where clause from filter criteria
            where_conditions = []
            
            if filter_criteria:
                if 'guild_id' in filter_criteria and filter_criteria['guild_id']:
                    where_conditions.append("m.guild_id = ?")
                    params.append(filter_criteria['guild_id'])
                
                if 'channel_id' in filter_criteria and filter_criteria['channel_id']:
                    where_conditions.append("m.channel_id = ?")
                    params.append(filter_criteria['channel_id'])
                
                if 'user_id' in filter_criteria and filter_criteria['user_id']:
                    where_conditions.append("m.user_id = ?")
                    params.append(filter_criteria['user_id'])
                
                if 'has_ai_response' in filter_criteria and filter_criteria['has_ai_response']:
                    where_conditions.append("ai.id IS NOT NULL")
                
                if 'search_text' in filter_criteria and filter_criteria['search_text']:
                    where_conditions.append("m.content LIKE ?")
                    params.append(f"%{filter_criteria['search_text']}%")
                
                if 'start_date' in filter_criteria and filter_criteria['start_date']:
                    where_conditions.append("m.timestamp >= ?")
                    params.append(filter_criteria['start_date'])
                
                if 'end_date' in filter_criteria and filter_criteria['end_date']:
                    where_conditions.append("m.timestamp <= ?")
                    params.append(filter_criteria['end_date'])
            
            # Add WHERE clause if we have conditions
            if where_conditions:
                query += " WHERE " + " AND ".join(where_conditions)
            
            # Add order by, limit and offset
            query += """
                ORDER BY m.timestamp DESC
                LIMIT ? OFFSET ?
            """
            
            params.append(limit)
            params.append(offset)
            
            # Execute the query
            cursor = await self.execute_query(query, params)
            if not cursor:
                return {"error": "Database query failed"}
            
            rows = cursor.fetchall()
            
            # Count total messages matching criteria (without limit/offset)
            count_query = """
                SELECT COUNT(*) FROM messages m
                LEFT JOIN ai_interactions ai ON m.id = ai.message_id
            """
            
            if where_conditions:
                count_query += " WHERE " + " AND ".join(where_conditions)
            
            count_cursor = await self.execute_query(count_query, params[:-2])  # Remove limit and offset params
            if not count_cursor:
                total_count = 0
            else:
                total_count = count_cursor.fetchone()[0]
            
            # Format results
            messages = []
            for row in rows:
                has_ai_response = bool(row[9])  # Check if ai_response is not empty
                
                message = {
                    "id": row[0],
                    "user_id": row[1],
                    "username": row[2],
                    "guild_id": row[3],
                    "guild_name": row[4],
                    "channel_id": row[5],
                    "channel_name": row[6],
                    "content": row[7],
                    "timestamp": row[8],
                    "has_ai_response": has_ai_response
                }
                
                # Add AI data if available
                if has_ai_response:
                    message["ai_data"] = {
                        "response": row[9],
                        "model": row[10],
                        "timestamp": row[11]
                    }
                    
                messages.append(message)
            
            return {
                "messages": messages,
                "total_count": total_count,
                "page_info": {
                    "limit": limit,
                    "offset": offset,
                    "has_more": total_count > (offset + limit)
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting message history: {e}", exc_info=True)
            return {"error": str(e)}