import logging
import json
import uuid
import time
from datetime import datetime
from utils.database import EncryptedDatabase

logger = logging.getLogger('discord_bot')

class AIInteractionLogger:
    """
    Logger for AI interactions with the bot, storing encrypted records of prompts and responses.
    This service captures all AI interactions including the full prompt and response.
    """
    
    def __init__(self, db_path, encryption_key):
        """
        Initialize the AI interaction logger.
        
        Args:
            db_path (str): Path to the SQLite database file
            encryption_key (str): Key used for encrypting sensitive data
        """
        self.db = EncryptedDatabase(db_path, encryption_key)
        logger.info("AIInteractionLogger initialized")
    
    async def log_interaction(self, user_id, guild_id, channel_id, model, prompt, response, 
                              tokens_used=None, execution_time=None, metadata=None):
        """
        Log an AI interaction to the database.
        
        Args:
            user_id (str): The Discord user ID
            guild_id (str): The Discord guild ID
            channel_id (str): The Discord channel ID
            model (str): The AI model used (e.g., "GPT-4o-mini")
            prompt (str): The user's prompt
            response (str): The AI's response
            tokens_used (int, optional): Number of tokens used
            execution_time (float, optional): Time taken to generate the response
            metadata (dict, optional): Additional metadata
        """
        try:
            # Generate a unique ID for this interaction
            interaction_id = str(uuid.uuid4())
            
            # Prepare the interaction data
            interaction_data = {
                'interaction_id': interaction_id,
                'user_id': str(user_id),
                'guild_id': str(guild_id),
                'channel_id': str(channel_id),
                'model': model,
                'prompt': prompt,
                'response': response,
                'timestamp': datetime.now().isoformat(),
                'tokens_used': tokens_used,
                'execution_time': execution_time,
                'metadata': json.dumps(metadata) if metadata else None
            }
            
            # Store in database using the queue to prevent concurrent access issues
            await self.db.queue.execute(lambda: self.db.store_ai_interaction(interaction_data))
            logger.debug(f"Logged AI interaction {interaction_id} from user {user_id}")
            
            return interaction_id
            
        except Exception as e:
            logger.error(f"Error logging AI interaction: {e}", exc_info=True)
            return None
    
    async def get_interaction(self, interaction_id):
        """
        Retrieve an AI interaction by ID.
        
        Args:
            interaction_id (str): The interaction ID
            
        Returns:
            dict: The interaction data or None if not found
        """
        try:
            # Use the queue to prevent concurrent access issues
            return await self.db.queue.execute(lambda: self.db.get_ai_interaction(interaction_id))
        except Exception as e:
            logger.error(f"Error retrieving AI interaction: {e}", exc_info=True)
            return None
    
    async def get_user_interactions(self, user_id, limit=100, offset=0):
        """
        Retrieve AI interactions for a specific user.
        
        Args:
            user_id (str): The Discord user ID
            limit (int): Maximum number of interactions to retrieve
            offset (int): Starting offset for pagination
            
        Returns:
            list: List of interaction data
        """
        try:
            # Use the queue to prevent concurrent access issues
            return await self.db.queue.execute(
                lambda: self.db.get_user_ai_interactions(user_id, limit, offset)
            )
        except Exception as e:
            logger.error(f"Error retrieving user AI interactions: {e}", exc_info=True)
            return []
    
    def close(self):
        """Close the database connection"""
        self.db.close()