"""
Simple data service for API access to the database.
Provides basic functionality without dashboard-specific components.
"""

import logging
import sqlite3
import json
from datetime import datetime, timedelta
from utils.logger import setup_logger

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
        logger.info("API data service initialized")

    async def get_dashboard_summary(self, filter_criteria=None):
        """Get dashboard summary statistics"""
        result = {
            "message_count": 0,
            "user_count": 0,
            "channel_count": 0,
            "ai_interaction_count": 0,
            "daily_messages": []
        }
        
        try:
            cursor = self.db.cursor()
            
            # Add WHERE clause if filter criteria provided
            where_clause = ""
            params = []
            if filter_criteria and 'guild_id' in filter_criteria and filter_criteria['guild_id']:
                where_clause = "WHERE guild_id = ?"
                params = [filter_criteria['guild_id']]
            
            # Count messages
            cursor.execute(f"SELECT COUNT(*) FROM messages {where_clause}", params)
            result["message_count"] = cursor.fetchone()[0]
            
            # Count unique users
            cursor.execute(f"SELECT COUNT(DISTINCT user_id) FROM messages {where_clause}", params)
            result["user_count"] = cursor.fetchone()[0]
            
            # Count channels
            cursor.execute(f"SELECT COUNT(DISTINCT channel_id) FROM messages {where_clause}", params)
            result["channel_count"] = cursor.fetchone()[0]
            
            # Count AI interactions (if table exists)
            try:
                cursor.execute(f"SELECT COUNT(*) FROM ai_interactions {where_clause}", params)
                result["ai_interaction_count"] = cursor.fetchone()[0]
            except sqlite3.OperationalError:
                # Table might not exist
                result["ai_interaction_count"] = 0
            
            # Get daily messages for the past 7 days
            seven_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            
            if where_clause:
                # If we already have a where clause, add AND
                date_query = f"""
                    SELECT DATE(timestamp) as date, COUNT(*) as count 
                    FROM messages 
                    {where_clause} AND DATE(timestamp) >= ?
                    GROUP BY DATE(timestamp)
                    ORDER BY date
                """
                cursor.execute(date_query, params + [seven_days_ago])
            else:
                # No existing where clause
                date_query = """
                    SELECT DATE(timestamp) as date, COUNT(*) as count 
                    FROM messages 
                    WHERE DATE(timestamp) >= ?
                    GROUP BY DATE(timestamp)
                    ORDER BY date
                """
                cursor.execute(date_query, [seven_days_ago])
            
            result["daily_messages"] = [{"date": row[0], "count": row[1]} for row in cursor.fetchall()]
            
            # Get top 3 active users
            if where_clause:
                user_query = f"""
                    SELECT user_name, COUNT(*) as message_count
                    FROM messages
                    {where_clause}
                    GROUP BY user_id
                    ORDER BY message_count DESC
                    LIMIT 3
                """
                cursor.execute(user_query, params)
            else:
                user_query = """
                    SELECT user_name, COUNT(*) as message_count
                    FROM messages
                    GROUP BY user_id
                    ORDER BY message_count DESC
                    LIMIT 3
                """
                cursor.execute(user_query)
            
            result["active_users"] = [{"username": row[0], "message_count": row[1]} for row in cursor.fetchall()]
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting dashboard summary: {e}")
            return result

    async def get_message_stats(self, filter_criteria=None, days=30):
        """Get message statistics"""
        result = {
            "daily_messages": [],
            "messages_by_channel": [],
            "hourly_activity": []
        }
        
        try:
            cursor = self.db.cursor()
            
            # Add WHERE clause if filter criteria provided
            where_clause = ""
            params = []
            if filter_criteria and 'guild_id' in filter_criteria and filter_criteria['guild_id']:
                where_clause = "WHERE guild_id = ?"
                params = [filter_criteria['guild_id']]
            
            # Get daily message counts
            days_ago = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            
            if where_clause:
                date_query = f"""
                    SELECT DATE(timestamp) as date, COUNT(*) as count 
                    FROM messages 
                    {where_clause} AND DATE(timestamp) >= ?
                    GROUP BY DATE(timestamp)
                    ORDER BY date
                """
                cursor.execute(date_query, params + [days_ago])
            else:
                date_query = """
                    SELECT DATE(timestamp) as date, COUNT(*) as count 
                    FROM messages 
                    WHERE DATE(timestamp) >= ?
                    GROUP BY DATE(timestamp)
                    ORDER BY date
                """
                cursor.execute(date_query, [days_ago])
            
            result["daily_messages"] = [{"date": row[0], "count": row[1]} for row in cursor.fetchall()]
            
            # Get messages by channel
            if where_clause:
                channel_query = f"""
                    SELECT channel_name, COUNT(*) as count
                    FROM messages
                    {where_clause}
                    GROUP BY channel_id
                    ORDER BY count DESC
                    LIMIT 10
                """
                cursor.execute(channel_query, params)
            else:
                channel_query = """
                    SELECT channel_name, COUNT(*) as count
                    FROM messages
                    GROUP BY channel_id
                    ORDER BY count DESC
                    LIMIT 10
                """
                cursor.execute(channel_query)
            
            result["messages_by_channel"] = [{"channel_name": row[0], "count": row[1]} for row in cursor.fetchall()]
            
            # Get hourly activity
            if where_clause:
                hourly_query = f"""
                    SELECT 
                        strftime('%H', timestamp) as hour,
                        strftime('%w', timestamp) as weekday_num,
                        COUNT(*) as count
                    FROM messages
                    {where_clause}
                    GROUP BY hour, weekday_num
                    ORDER BY weekday_num, hour
                """
                cursor.execute(hourly_query, params)
            else:
                hourly_query = """
                    SELECT 
                        strftime('%H', timestamp) as hour,
                        strftime('%w', timestamp) as weekday_num,
                        COUNT(*) as count
                    FROM messages
                    GROUP BY hour, weekday_num
                    ORDER BY weekday_num, hour
                """
                cursor.execute(hourly_query)
            
            weekdays = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
            result["hourly_activity"] = [
                {"hour": int(row[0]), "weekday": weekdays[int(row[1])], "count": row[2]}
                for row in cursor.fetchall()
            ]
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting message stats: {e}")
            return result

    async def get_user_stats(self, filter_criteria=None, limit=10):
        """Get user statistics"""
        result = {
            "active_users": [],
            "user_roles": [],
            "user_growth": []
        }
        
        try:
            cursor = self.db.cursor()
            
            # Add WHERE clause if filter criteria provided
            where_clause = ""
            params = []
            if filter_criteria and 'guild_id' in filter_criteria and filter_criteria['guild_id']:
                where_clause = "WHERE guild_id = ?"
                params = [filter_criteria['guild_id']]
            
            # Get active users
            if where_clause:
                users_query = f"""
                    SELECT user_name, COUNT(*) as message_count
                    FROM messages
                    {where_clause}
                    GROUP BY user_id
                    ORDER BY message_count DESC
                    LIMIT ?
                """
                cursor.execute(users_query, params + [limit])
            else:
                users_query = """
                    SELECT user_name, COUNT(*) as message_count
                    FROM messages
                    GROUP BY user_id
                    ORDER BY message_count DESC
                    LIMIT ?
                """
                cursor.execute(users_query, [limit])
            
            result["active_users"] = [{"username": row[0], "message_count": row[1]} for row in cursor.fetchall()]
            
            # Simplified mock data for user roles and growth since we may not track these
            result["user_roles"] = [
                {"role": "Member", "count": result["active_users"][0]["message_count"] if result["active_users"] else 0}
            ]
            
            # User growth over past 5 weeks
            weeks_ago = []
            for i in range(5):
                weeks_ago.append((datetime.now() - timedelta(weeks=i)).strftime('%Y-%m-%d'))
            
            result["user_growth"] = [
                {"date": date, "count": i * 10 + 30} for i, date in enumerate(reversed(weeks_ago))
            ]
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return result

    async def get_ai_stats(self, filter_criteria=None, days=30):
        """Get AI interaction statistics"""
        result = {
            "ai_models": [],
            "ai_daily": [],
            "ai_users": []
        }
        
        try:
            # Get the correct database connection for AI interactions
            ai_db = None
            
            # First, try to access the AI database directly from the bot's message monitor
            if hasattr(self.db, 'get_ai_database'):
                ai_db = self.db.get_ai_database()
            
            # If that doesn't work, try to see if there's an ai_db attribute
            if not ai_db and hasattr(self.db, 'ai_db'):
                ai_db = self.db.ai_db
            
            if ai_db:
                # Use the AI database connection if available
                logger.info("Using dedicated AI interactions database connection for AI stats")
                cursor = ai_db.cursor()
            else:
                # Fall back to the main database connection
                logger.warning("AI database connection not found, using main database connection for AI stats")
                cursor = self.db.cursor()
            
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
        """Get all messages from the database"""
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM messages ORDER BY timestamp DESC LIMIT 1000")
            columns = [column[0] for column in cursor.description]
            messages = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return messages
        except Exception as e:
            logger.error(f"Error getting messages: {e}")
            return []

    async def get_all_files(self):
        """Get all files from the database"""
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM files ORDER BY timestamp DESC LIMIT 1000")
            columns = [column[0] for column in cursor.description]
            files = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return files
        except Exception as e:
            logger.error(f"Error getting files: {e}")
            return []

    async def get_all_reactions(self):
        """Get all reactions from the database"""
        try:
            cursor = self.db.cursor()
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
            cursor = self.db.cursor()
            
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
            cursor = self.db.cursor()
            
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
            # Check if we're running in the API server mode with separate AI database
            ai_db = None
            
            # First, try to access the AI database directly from the bot's message monitor
            if hasattr(self.db, 'get_ai_database'):
                ai_db = self.db.get_ai_database()
            
            # If that doesn't work, try to see if there's an ai_db attribute
            if not ai_db and hasattr(self.db, 'ai_db'):
                ai_db = self.db.ai_db
            
            if ai_db:
                # Use the AI database connection if available
                logger.info("Using dedicated AI interactions database connection")
                cursor = ai_db.cursor()
            else:
                # Fall back to the main database connection
                logger.warning("AI database connection not found, using main database connection")
                cursor = self.db.cursor()
            
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