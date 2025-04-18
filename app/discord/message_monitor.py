import discord
import logging
import json
import uuid
import re
import os
import asyncio
import aiohttp
import time
from datetime import datetime
from utils.database import EncryptedDatabase

# Optional AI vision imports - will be imported dynamically if configured
vision_imports_successful = False
try:
    from PIL import Image
    import io
    import requests
    import base64
    vision_imports_successful = True
except ImportError:
    pass

logger = logging.getLogger('discord_bot')

class MessageMonitor:
    """
    Monitor and log all Discord messages in an encrypted database.
    This service captures all messages across all channels the bot has access to.
    """
    
    def __init__(self, client, db_path, encryption_key, vision_api_key=None):
        """
        Initialize the message monitor service.
        
        Args:
            client (discord.Client): The Discord client object
            db_path (str): Path to the SQLite database file
            encryption_key (str): Key used for encrypting sensitive data
            vision_api_key (str, optional): API key for vision AI services
        """
        self.client = client
        self.db = EncryptedDatabase(db_path, encryption_key)
        self.vision_api_key = vision_api_key
        self.ai_analysis_enabled = vision_imports_successful and vision_api_key is not None
        
        # Cache for improving performance
        self._cache = {
            'statistics': {'data': None, 'timestamp': 0},
            'recent_messages': {'data': None, 'timestamp': 0},
            'user_activity': {'data': None, 'timestamp': 0},
            'file_types': {'data': None, 'timestamp': 0}
        }
        self._cache_ttl = 300  # 5 minutes cache lifetime
        
        if self.ai_analysis_enabled:
            logger.info("MessageMonitor initialized with AI content analysis")
        else:
            if vision_api_key is None:
                logger.info("MessageMonitor initialized without AI content analysis (no API key provided)")
            elif not vision_imports_successful:
                logger.info("MessageMonitor initialized without AI content analysis (required packages not installed)")
            else:
                logger.info("MessageMonitor initialized without AI content analysis")
        
        # Register message event handler
        @client.event
        async def on_message(message):
            await self.process_message(message)
    
    async def process_message(self, message):
        """
        Process and store a Discord message.
        
        Args:
            message (discord.Message): The Discord message object
        """
        try:
            # Skip messages from the bot itself to avoid circular logging
            if message.author == self.client.user:
                return
                
            # Skip messages from any bot, as they'll be logged in AI interactions if relevant
            if message.author.bot:
                logger.debug(f"Skipping message from bot {message.author.name} (ID: {message.author.id})")
                return
                
            # Extract all relevant data from the message
            attachments_data = []
            for attachment in message.attachments:
                attachments_data.append({
                    'id': str(attachment.id),
                    'filename': attachment.filename,
                    'url': attachment.url,
                    'size': attachment.size,
                    'content_type': attachment.content_type if hasattr(attachment, 'content_type') else None
                })
                
            # Format mentions for metadata
            mentions = {
                'users': [str(user.id) for user in message.mentions],
                'roles': [str(role.id) for role in message.role_mentions],
                'channels': [str(channel.id) for channel in message.channel_mentions]
            }
            
            # Get additional message flags and properties
            message_flags = {}
            for flag_name in dir(message.flags):
                if not flag_name.startswith('_') and isinstance(getattr(message.flags, flag_name), bool):
                    message_flags[flag_name] = getattr(message.flags, flag_name)
            
            # Create the message data dictionary
            message_data = {
                'message_id': str(message.id),
                'channel_id': str(message.channel.id),
                'guild_id': str(message.guild.id) if message.guild else "DM",
                'author_id': str(message.author.id),
                'author_name': f"{message.author.name}#{message.author.discriminator}" if hasattr(message.author, 'discriminator') else message.author.name,
                'content': message.content,
                'timestamp': message.created_at.isoformat(),
                'attachments': json.dumps(attachments_data) if attachments_data else None,
                'message_type': str(message.type.name) if hasattr(message.type, 'name') else str(message.type),
                'is_bot': message.author.bot,
                'metadata': json.dumps({
                    'mentions': mentions,
                    'embeds_count': len(message.embeds),
                    'flags': message_flags,
                    'pinned': message.pinned,
                    'system_content': message.system_content if hasattr(message, 'system_content') else None,
                    'reference': str(message.reference.message_id) if message.reference else None
                })
            }
            
            # Store message in database using the queue to prevent concurrent access issues
            await self.db.queue.execute(lambda: self.db.store_message(message_data))
            logger.debug(f"Stored message {message.id} from user {message.author.name}")
            
            # Invalidate cache for dashboard data
            self._invalidate_cache('statistics')
            self._invalidate_cache('recent_messages')
            self._invalidate_cache('user_activity')
            
            # Use message_id consistently to ensure proper association
            message_id = str(message.id)
            
            # Download and store attachments and images/files from links
            downloaded_files = await self.db.store_message_files(message_data)
            file_analysis_tasks = []
            
            # Extract and download URLs from embeds
            if message.embeds:
                for embed in message.embeds:
                    # Check for image URLs in embeds
                    if embed.image and embed.image.url:
                        filename = embed.image.url.split('/')[-1].split('?')[0]
                        file_id = await self.db.download_url(
                            embed.image.url, 
                            filename, 
                            message_id,  # Explicitly use message_id to ensure association
                            str(message.channel.id),
                            str(message.guild.id) if message.guild else "DM", 
                            str(message.author.id)
                        )
                        if file_id:
                            downloaded_files.append(file_id)
                            if self.ai_analysis_enabled:
                                file_analysis_tasks.append(self.analyze_file_content(file_id))
                    
                    # Check for thumbnail URLs in embeds
                    if embed.thumbnail and embed.thumbnail.url:
                        filename = embed.thumbnail.url.split('/')[-1].split('?')[0]
                        file_id = await self.db.download_url(
                            embed.thumbnail.url, 
                            filename, 
                            message_id,  # Explicitly use message_id to ensure association
                            str(message.channel.id),
                            str(message.guild.id) if message.guild else "DM", 
                            str(message.author.id)
                        )
                        if file_id:
                            downloaded_files.append(file_id)
                            if self.ai_analysis_enabled:
                                file_analysis_tasks.append(self.analyze_file_content(file_id))
                    
                    # Check for other URLs in embed fields
                    if embed.description:
                        embed_file_ids = await self._extract_and_download_urls(
                            embed.description,
                            message_id,
                            str(message.channel.id),
                            str(message.guild.id) if message.guild else "DM",
                            str(message.author.id)
                        )
                        downloaded_files.extend(embed_file_ids)
                        if self.ai_analysis_enabled:
                            for file_id in embed_file_ids:
                                file_analysis_tasks.append(self.analyze_file_content(file_id))
                    
                    # Check fields for URLs
                    if embed.fields:
                        for field in embed.fields:
                            field_file_ids = await self._extract_and_download_urls(
                                field.value,
                                message_id,
                                str(message.channel.id),
                                str(message.guild.id) if message.guild else "DM",
                                str(message.author.id)
                            )
                            downloaded_files.extend(field_file_ids)
                            if self.ai_analysis_enabled:
                                for file_id in field_file_ids:
                                    file_analysis_tasks.append(self.analyze_file_content(file_id))
            
            # Extract and download URLs from message content
            if message.content:
                content_file_ids = await self._extract_and_download_urls(
                    message.content,
                    message_id,
                    str(message.channel.id),
                    str(message.guild.id) if message.guild else "DM",
                    str(message.author.id)
                )
                downloaded_files.extend(content_file_ids)
                if self.ai_analysis_enabled:
                    for file_id in content_file_ids:
                        file_analysis_tasks.append(self.analyze_file_content(file_id))
            
            # Log the download completion
            if downloaded_files:
                logger.info(f"Downloaded {len(downloaded_files)} files from message {message_id}")
                # Invalidate file types cache
                self._invalidate_cache('file_types')
            
            # Analyze all downloaded files in parallel if AI analysis is enabled
            if self.ai_analysis_enabled and file_analysis_tasks:
                logger.debug(f"Starting AI analysis for {len(file_analysis_tasks)} files")
                await asyncio.gather(*file_analysis_tasks)
                logger.info(f"Completed AI analysis for {len(file_analysis_tasks)} files from message {message_id}")
            
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
    
    def _invalidate_cache(self, cache_key):
        """
        Invalidate a specific cache entry.
        
        Args:
            cache_key (str): The cache key to invalidate
        """
        if cache_key in self._cache:
            self._cache[cache_key]['data'] = None
            self._cache[cache_key]['timestamp'] = 0
    
    def _get_from_cache(self, cache_key):
        """
        Get data from cache if available and not expired.
        
        Args:
            cache_key (str): The cache key to retrieve
            
        Returns:
            tuple: (data, is_cached) where is_cached is a boolean indicating if data came from cache
        """
        cache_entry = self._cache.get(cache_key)
        if not cache_entry:
            return None, False
            
        current_time = time.time()
        if cache_entry['data'] and (current_time - cache_entry['timestamp'] < self._cache_ttl):
            return cache_entry['data'], True
            
        return None, False
    
    def _update_cache(self, cache_key, data):
        """
        Update cache with new data.
        
        Args:
            cache_key (str): The cache key to update
            data: The data to store in cache
        """
        if cache_key in self._cache:
            self._cache[cache_key]['data'] = data
            self._cache[cache_key]['timestamp'] = time.time()
    
    async def _extract_and_download_urls(self, text, message_id, channel_id, guild_id, author_id):
        """
        Extract URLs from text and download files if they match common media types.
        
        Args:
            text (str): Text to scan for URLs
            message_id (str): ID of the message containing the URLs
            channel_id (str): ID of the channel
            guild_id (str): ID of the guild
            author_id (str): ID of the message author
            
        Returns:
            list: List of downloaded file IDs
        """
        # Common file extensions to download
        file_extensions = [
            '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg',  # Images
            '.mp4', '.webm', '.mov', '.avi', '.wmv',  # Videos
            '.mp3', '.wav', '.ogg', '.flac',  # Audio
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',  # Documents
            '.zip', '.rar', '.7z', '.tar', '.gz'  # Archives
        ]
        
        # Extract URLs using regex
        urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)
        downloaded_file_ids = []
        
        for url in urls:
            # Check if the URL ends with one of the file extensions
            if any(url.lower().endswith(ext) for ext in file_extensions):
                # Generate a filename from the URL
                filename = url.split('/')[-1].split('?')[0]
                file_id = await self.db.download_url(
                    url,
                    filename,
                    message_id,  # Always associate with the original message
                    channel_id,
                    guild_id,
                    author_id
                )
                if file_id:
                    downloaded_file_ids.append(file_id)
                    
        return downloaded_file_ids
        
    async def analyze_file_content(self, file_id):
        """
        Analyze the content of a file using AI services and update its metadata.
        
        Args:
            file_id (str): The ID of the file to analyze
        """
        try:
            # Skip if AI analysis is not enabled
            if not self.ai_analysis_enabled:
                return
                
            # Get file information from database
            file_info = await self.db.get_file_info(file_id)
            if not file_info:
                logger.warning(f"Could not find file info for file_id: {file_id}")
                return
                
            file_path = file_info.get('file_path')
            file_type = file_info.get('file_type', '').lower()
            
            if not file_path or not os.path.exists(file_path):
                logger.warning(f"File path does not exist: {file_path}")
                return
                
            # Only analyze images for now
            image_types = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp']
            if file_type in image_types:
                # Analyze image content
                content_description = await self._analyze_image(file_path)
                if content_description:
                    # Update file metadata with AI analysis
                    categories = self._categorize_content(content_description)
                    suggested_name = self._generate_descriptive_name(file_path, content_description)
                    
                    # Update file metadata in database
                    metadata = {
                        'ai_description': content_description,
                        'categories': categories,
                        'suggested_name': suggested_name,
                        'analyzed_at': datetime.now().isoformat()
                    }
                    
                    await self.db.update_file_metadata(file_id, metadata)
                    logger.info(f"Updated file {file_id} with AI analysis: {', '.join(categories)}")
            
            # For document analysis, we would add handlers for different file types here
            # elif file_type in ['pdf', 'doc', 'docx']:
            #     # Analyze document content
            #     pass
            
        except Exception as e:
            logger.error(f"Error analyzing file content: {e}", exc_info=True)
    
    async def _analyze_image(self, file_path):
        """
        Analyze an image using Google Gemini vision API.
        
        Args:
            file_path (str): Path to the image file
            
        Returns:
            str: Description of the image content
        """
        try:
            # Skip if we don't have the required imports
            if not vision_imports_successful:
                return None
                
            if not self.vision_api_key:
                logger.debug("No Gemini API key provided for image analysis")
                return None
                
            # Open the image file
            image = Image.open(file_path)
            
            # Resize image if too large for API
            max_size = (1024, 1024)
            if image.width > max_size[0] or image.height > max_size[1]:
                image.thumbnail(max_size)
            
            # Convert to bytes for API request
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format=image.format or 'JPEG')
            img_byte_arr.seek(0)
            
            # Google Gemini API call
            api_url = "https://generativelanguage.googleapis.com/v1/models/gemini-pro-vision:generateContent"
            
            # Prepare the request payload
            import base64
            
            # Convert image to base64
            encoded_image = base64.b64encode(img_byte_arr.read()).decode('utf-8')
            
            payload = {
                "contents": [{
                    "parts": [
                        {"text": "Describe this image in detail. Focus on the content, objects, people, animals, scenery, or any other elements."},
                        {
                            "inline_data": {
                                "mime_type": f"image/{image.format.lower() if image.format else 'jpeg'}",
                                "data": encoded_image
                            }
                        }
                    ]
                }]
            }
            
            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": self.vision_api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # Extract the response text from Gemini
                        try:
                            description = result['candidates'][0]['content']['parts'][0]['text']
                            logger.info(f"Gemini successfully analyzed image: {file_path}")
                            return description
                        except (KeyError, IndexError) as e:
                            logger.error(f"Failed to extract description from Gemini response: {e}")
                            return None
                    else:
                        error_text = await response.text()
                        logger.warning(f"Gemini API returned status code {response.status}: {error_text}")
                        return None
                
        except Exception as e:
            logger.error(f"Error in Gemini image analysis: {e}", exc_info=True)
            return None
    
    def _categorize_content(self, description):
        """
        Categorize content based on AI description.
        
        Args:
            description (str): AI-generated description of content
            
        Returns:
            list: Categories that match the content
        """
        # Define category keywords
        categories = {
            'people': ['person', 'people', 'face', 'man', 'woman', 'child', 'group'],
            'nature': ['nature', 'landscape', 'mountain', 'beach', 'forest', 'tree', 'ocean', 'sky'],
            'animals': ['animal', 'dog', 'cat', 'bird', 'wildlife', 'pet'],
            'food': ['food', 'meal', 'restaurant', 'dinner', 'lunch', 'breakfast', 'cooking'],
            'technology': ['computer', 'phone', 'device', 'screen', 'technology', 'software'],
            'art': ['art', 'drawing', 'painting', 'artwork', 'sculpture', 'creative'],
            'document': ['document', 'text', 'paper', 'writing', 'letter', 'form'],
            'screenshot': ['screenshot', 'screen', 'interface', 'ui', 'app'],
            'meme': ['meme', 'funny', 'joke', 'humor'],
            'diagram': ['diagram', 'chart', 'graph', 'flowchart', 'schematic']
        }
        
        # Match description with categories
        matched_categories = []
        description_lower = description.lower()
        
        for category, keywords in categories.items():
            if any(keyword in description_lower for keyword in keywords):
                matched_categories.append(category)
        
        return matched_categories or ['uncategorized']
    
    def _generate_descriptive_name(self, file_path, description):
        """
        Generate a descriptive filename based on content analysis.
        
        Args:
            file_path (str): Original file path
            description (str): AI-generated description of content
            
        Returns:
            str: Suggested descriptive filename
        """
        # Extract important keywords from description
        # In a real implementation, you might use NLP techniques like keyword extraction
        keywords = [word.lower() for word in description.split() if len(word) > 3]
        keywords = keywords[:3]  # Take up to 3 keywords
        
        # Get original file extension
        original_name = os.path.basename(file_path)
        _, extension = os.path.splitext(original_name)
        
        # Generate timestamp
        timestamp = datetime.now().strftime("%Y%m%d")
        
        # Combine elements into a new filename
        if keywords:
            suggested_name = f"{'-'.join(keywords)}_{timestamp}{extension}"
        else:
            suggested_name = f"content_{timestamp}{extension}"
            
        return suggested_name
    
    async def get_dashboard_data(self):
        """
        Get data for the dashboard with optimal log(n) performance.
        Utilizes caching to minimize database queries.
        
        Returns:
            dict: Dashboard data including statistics and recent activity
        """
        # Get cached statistics or retrieve new ones
        statistics, is_cached = self._get_from_cache('statistics')
        if not is_cached:
            statistics = self.db.get_statistics()
            self._update_cache('statistics', statistics)
        
        # Get cached recent messages or retrieve new ones
        recent_messages, is_cached = self._get_from_cache('recent_messages')
        if not is_cached:
            # Use indexed query with limit for O(log n) complexity
            recent_messages = self.db.get_recent_messages(limit=25)
            self._update_cache('recent_messages', recent_messages)
        
        # Get cached user activity or retrieve new ones
        user_activity, is_cached = self._get_from_cache('user_activity')
        if not is_cached:
            # Get user activity metrics with indexed queries
            user_activity = self.db.get_active_users(limit=10)
            self._update_cache('user_activity', user_activity)
        
        # Get cached file type distribution or retrieve new ones
        file_types, is_cached = self._get_from_cache('file_types')
        if not is_cached:
            # Build file type distribution with indexed query
            file_types = statistics.get('file_types', {})
            self._update_cache('file_types', file_types)
        
        # Compile all dashboard data
        dashboard_data = {
            'statistics': statistics,
            'recent_messages': recent_messages,
            'user_activity': user_activity,
            'file_types': file_types,
            'last_updated': datetime.now().isoformat()
        }
        
        return dashboard_data
    
    async def search_messages(self, query, filter_criteria=None, limit=100, offset=0):
        """
        Search messages using indexed fields for O(log n) search performance.
        
        Args:
            query (str): The search query
            filter_criteria (dict): Optional filters like user_id, channel_id, etc.
            limit (int): Maximum results to return
            offset (int): Pagination offset
            
        Returns:
            dict: Search results with pagination info
        """
        start_time = time.time()
        results = self.db.search_messages(query, filter_criteria=filter_criteria, limit=limit, offset=offset)
        
        return {
            'results': results,
            'count': len(results),
            'execution_time': time.time() - start_time,
            'has_more': len(results) >= limit,
            'query': query,
            'filters': filter_criteria
        }
    
    def close(self):
        """Close the database connection"""
        self.db.close()

    async def process_message_edit(self, before, after):
        """
        Process and store an edited Discord message.
        
        Args:
            before (discord.Message): The Discord message before edit
            after (discord.Message): The Discord message after edit
        """
        try:
            # Skip messages from the bot itself to avoid circular logging
            if after.author == self.client.user:
                return
                
            # Skip messages from any bot
            if after.author.bot:
                logger.debug(f"Skipping edited message from bot {after.author.name} (ID: {after.author.id})")
                return
                
            # Extract message data for the edited message
            attachments_data = []
            for attachment in after.attachments:
                attachments_data.append({
                    'id': str(attachment.id),
                    'filename': attachment.filename,
                    'url': attachment.url,
                    'size': attachment.size,
                    'content_type': attachment.content_type if hasattr(attachment, 'content_type') else None
                })
                
            # Format mentions for metadata
            mentions = {
                'users': [str(user.id) for user in after.mentions],
                'roles': [str(role.id) for role in after.role_mentions],
                'channels': [str(channel.id) for channel in after.channel_mentions]
            }
            
            # Get additional message flags and properties
            message_flags = {}
            for flag_name in dir(after.flags):
                if not flag_name.startswith('_') and isinstance(getattr(after.flags, flag_name), bool):
                    message_flags[flag_name] = getattr(after.flags, flag_name)
            
            # Create the edit history entry
            edit_data = {
                'edit_id': str(uuid.uuid4()),
                'message_id': str(after.id),
                'channel_id': str(after.channel.id),
                'guild_id': str(after.guild.id) if after.guild else "DM",
                'author_id': str(after.author.id),
                'before_content': before.content,
                'after_content': after.content,
                'edit_timestamp': datetime.now().isoformat(),
                'attachments': json.dumps(attachments_data) if attachments_data else None,
                'metadata': json.dumps({
                    'mentions': mentions,
                    'embeds_count': len(after.embeds),
                    'flags': message_flags,
                    'pinned': after.pinned,
                    'system_content': after.system_content if hasattr(after, 'system_content') else None,
                    'reference': str(after.reference.message_id) if after.reference else None
                })
            }
            
            # Store edit history in database
            await self.db.queue.execute(lambda: self.db.store_message_edit(edit_data))
            logger.debug(f"Stored edit for message {after.id} from user {after.author.name}")
            
            # Invalidate cache for dashboard data
            self._invalidate_cache('statistics')
            self._invalidate_cache('recent_messages')
            self._invalidate_cache('user_activity')
            
            # Check for new attachments or file URLs that weren't in the original message
            downloaded_files = []
            file_analysis_tasks = []
            
            # Handle new attachments
            for attachment in after.attachments:
                # Check if this attachment wasn't in the original message
                if not any(a.id == attachment.id for a in before.attachments):
                    file_path = await self.db.download_attachment(
                        attachment, 
                        str(after.id), 
                        str(after.channel.id),
                        str(after.guild.id) if after.guild else "DM",
                        str(after.author.id),
                        is_edit=True
                    )
                    if file_path:
                        file_id = os.path.basename(file_path).split('.')[0]
                        downloaded_files.append(file_id)
                        if self.ai_analysis_enabled:
                            file_analysis_tasks.append(self.analyze_file_content(file_id))
            
            # Extract and download new URLs from edited message content
            if after.content != before.content:
                content_file_ids = await self._extract_and_download_urls(
                    after.content,
                    str(after.id),
                    str(after.channel.id),
                    str(after.guild.id) if after.guild else "DM",
                    str(after.author.id),
                    is_edit=True
                )
                downloaded_files.extend(content_file_ids)
                if self.ai_analysis_enabled:
                    for file_id in content_file_ids:
                        file_analysis_tasks.append(self.analyze_file_content(file_id))
            
            # Log the download completion for new files
            if downloaded_files:
                logger.info(f"Downloaded {len(downloaded_files)} new files from edited message {after.id}")
                # Invalidate file types cache
                self._invalidate_cache('file_types')
            
            # Analyze all newly downloaded files in parallel if AI analysis is enabled
            if self.ai_analysis_enabled and file_analysis_tasks:
                logger.debug(f"Starting AI analysis for {len(file_analysis_tasks)} files from edited message")
                await asyncio.gather(*file_analysis_tasks)
                logger.info(f"Completed AI analysis for {len(file_analysis_tasks)} files from edited message {after.id}")
            
        except Exception as e:
            logger.error(f"Error processing message edit: {e}", exc_info=True)