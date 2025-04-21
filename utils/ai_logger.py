import logging
import json
import uuid
from datetime import datetime
from utils.database import UnifiedDatabase

logger = logging.getLogger('discord_bot')

class AIInteractionLogger:
    """
    Logger for AI interactions with the bot, storing encrypted records of prompts and responses.
    This service captures all AI interactions including the full prompt and response.
    """
    
    def __init__(self, db, encryption_key=None):
        """
        Initialize the AI interaction logger.
        
        Args:
            db (UnifiedDatabase): The database instance to use
            encryption_key (str, optional): Key for encrypting sensitive data, used only if creating a new db
        """
        if isinstance(db, str):
            # For backward compatibility, if a string path is provided
            logger.debug(f"Creating new database instance at path: {db}")
            self.db = UnifiedDatabase(db, encryption_key)
        else:
            # Use the provided database instance
            logger.debug("Using provided database instance")
            self.db = db
        logger.debug("AIInteractionLogger initialized.")
    
    async def store_ai_interaction(self, interaction_data):
        """
        Store an AI interaction directly (compatible with MessageMonitor).
        
        Args:
            interaction_data (dict): AI interaction data dict
            
        Returns:
            bool: Success status
        """
        logger.debug(f"store_ai_interaction called with data for user {interaction_data.get('user_id', 'unknown')}")
        try:
            # Generate a unique ID if not provided
            if 'interaction_id' not in interaction_data:
                interaction_data['interaction_id'] = str(uuid.uuid4())
                
            # Add timestamp if not provided
            if 'timestamp' not in interaction_data:
                interaction_data['timestamp'] = datetime.now().isoformat()
            
            # Store in database
            await self.db.store_ai_interaction(interaction_data)
            logger.debug(f"Interaction {interaction_data['interaction_id']} stored successfully via store_ai_interaction")
            return True
        except Exception as e:
            logger.error(f"Error storing AI interaction: {str(e)}", exc_info=True)
            return False
    
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
        logger.debug(f"Logging AI interaction for user {user_id} in guild {guild_id}, channel {channel_id} with model {model}.")
        try:
            # Generate a unique ID for this interaction
            interaction_id = str(uuid.uuid4())
            logger.debug(f"Generated interaction ID: {interaction_id}")
            
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
                'metadata': metadata
            }
            logger.debug("Prepared interaction data dictionary.")
            
            # Store in database
            logger.debug(f"Storing interaction {interaction_id} in database.")
            await self.db.store_ai_interaction(interaction_data)
            logger.debug(f"Interaction {interaction_id} stored successfully.")
            return interaction_id
            
        except Exception as e:
            logger.error(f"Error logging AI interaction: {str(e)}", exc_info=True)
            return None
    
    async def get_interaction(self, interaction_id):
        """
        Retrieve an AI interaction by ID.
        
        Args:
            interaction_id (str): The interaction ID
            
        Returns:
            dict: The interaction data or None if not found
        """
        logger.debug(f"Retrieving AI interaction with ID: {interaction_id}")
        try:
            result = await self.db.get_ai_interaction(interaction_id)
            logger.debug(f"Retrieved interaction {interaction_id}. Found: {result is not None}")
            return result
        except Exception as e:
            logger.error(f"Error retrieving AI interaction {interaction_id}: {str(e)}", exc_info=True)
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
        logger.debug(f"Retrieving AI interactions for user {user_id} with limit={limit}, offset={offset}.")
        try:
            results = await self.db.get_user_ai_interactions(user_id, limit, offset)
            logger.debug(f"Retrieved {len(results)} interactions for user {user_id}.")
            return results
        except Exception as e:
            logger.error(f"Error retrieving user AI interactions for {user_id}: {str(e)}", exc_info=True)
            return []
    
    async def close(self):
        """Close the database connection if this instance owns it."""
        # The decision logic is handled in DiscordBot.cleanup
        # This method is called only if this instance is responsible for closing.
        logger.debug("Attempting to close AIInteractionLogger database connection...")
        try:
            if hasattr(self, 'db') and self.db:
                await self.db.close()
                logger.debug("AIInteractionLogger database connection closed.")
            else:
                logger.debug("AIInteractionLogger has no database connection to close.")
        except Exception as e:
            logger.error(f"Error closing AIInteractionLogger database: {e}", exc_info=True)
            
    async def process_message_edit(self, before, after):
        """
        Process a message edit event (stub method for compatibility).
        
        Args:
            before: Message before edit
            after: Message after edit
            
        Returns:
            bool: Always returns True
        """
        logger.debug(f"process_message_edit called on AIInteractionLogger (stub method)")
        # This is a stub method to prevent errors when this object is used in place of MessageMonitor
        return True