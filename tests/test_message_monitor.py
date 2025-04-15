import unittest
from unittest.mock import Mock, patch, AsyncMock, MagicMock, call
import json
import discord
from discord import Embed, Attachment
import io
import sys
import os
from app.discord.message_monitor import MessageMonitor

# Import the MessageMonitor class from the main application

class TestMessageMonitor(unittest.TestCase):
    def setUp(self):
        # Mock the Discord client
        self.mock_client = Mock(spec=discord.Client)
        self.mock_client.user = Mock()
        
        # Mock the EncryptedDatabase
        self.patcher = patch('message_monitor.EncryptedDatabase')
        self.mock_db_class = self.patcher.start()
        self.mock_db = self.mock_db_class.return_value
        self.mock_db.store_message = Mock()
        self.mock_db.store_message_files = AsyncMock(return_value=[])
        self.mock_db.download_url = AsyncMock(return_value="file_id_123")
        self.mock_db.get_file_info = AsyncMock()
        self.mock_db.update_file_metadata = AsyncMock(return_value=True)
        
        # Initialize MessageMonitor with mocks
        self.message_monitor = MessageMonitor(
            self.mock_client, 
            "test_db.sqlite", 
            "test_key"
        )
        
        # Initialize with vision API for tests that need it
        self.message_monitor_with_vision = MessageMonitor(
            self.mock_client, 
            "test_db.sqlite", 
            "test_key",
            vision_api_key="test_gemini_api_key"
        )
        # Patch the vision_imports_successful to True for testing
        with patch('message_monitor.vision_imports_successful', True):
            self.message_monitor_with_vision.ai_analysis_enabled = True
    
    def tearDown(self):
        self.patcher.stop()
        
    def test_init(self):
        """Test that MessageMonitor initializes correctly"""
        self.assertEqual(self.message_monitor.client, self.mock_client)
        self.assertEqual(self.message_monitor.db, self.mock_db)
        self.mock_db_class.assert_called_once_with("test_db.sqlite", "test_key")
    
    @patch('message_monitor.logger')
    def test_close(self, mock_logger):
        """Test that close method calls db.close"""
        self.message_monitor.close()
        self.mock_db.close.assert_called_once()
    
    @patch('message_monitor.logger')
    async def test_process_message_skips_own_messages(self, mock_logger):
        """Test that messages from the bot itself are skipped"""
        # Create a mock message
        mock_message = AsyncMock()
        mock_message.author = self.mock_client.user
        
        # Process the message
        await self.message_monitor.process_message(mock_message)
        
        # Verify that store_message was not called
        self.mock_db.store_message.assert_not_called()
    
    @patch('message_monitor.logger')
    async def test_process_message_basic(self, mock_logger):
        """Test processing a basic message with no attachments or embeds"""
        # Create a mock message
        mock_message = AsyncMock()
        mock_message.author = Mock()
        mock_message.author.bot = False
        mock_message.author.name = "TestUser"
        mock_message.author.discriminator = "1234"
        mock_message.author.id = "12345"
        mock_message.id = "67890"
        mock_message.channel.id = "channel123"
        mock_message.guild = Mock()
        mock_message.guild.id = "guild456"
        mock_message.content = "Hello, world!"
        mock_message.created_at.isoformat.return_value = "2023-01-01T12:00:00"
        mock_message.attachments = []
        mock_message.embeds = []
        mock_message.mentions = []
        mock_message.role_mentions = []
        mock_message.channel_mentions = []
        mock_message.type = Mock()
        mock_message.type.name = "default"
        mock_message.pinned = False
        mock_message.reference = None
        mock_message.flags = Mock()
        
        # Set up flag behavior
        def getattr_side_effect(obj, name):
            if name == "suppress_embeds":
                return False
            raise AttributeError(f"'{type(obj).__name__}' object has no attribute '{name}'")
        
        mock_message.flags.__getattr__ = Mock(side_effect=getattr_side_effect)
        mock_message.flags.suppress_embeds = False
        
        # Process the message
        await self.message_monitor.process_message(mock_message)
        
        # Verify that store_message was called with the right data
        self.mock_db.store_message.assert_called_once()
        call_args = self.mock_db.store_message.call_args[0][0]
        
        self.assertEqual(call_args['message_id'], "67890")
        self.assertEqual(call_args['channel_id'], "channel123")
        self.assertEqual(call_args['guild_id'], "guild456")
        self.assertEqual(call_args['author_id'], "12345")
        self.assertEqual(call_args['author_name'], "TestUser#1234")
        self.assertEqual(call_args['content'], "Hello, world!")
        
    @patch('message_monitor.logger')
    async def test_process_message_with_attachments(self, mock_logger):
        """Test processing a message with attachments"""
        # Create a mock message with attachments
        mock_message = AsyncMock()
        mock_message.author = Mock()
        mock_message.author.bot = False
        mock_message.author.name = "TestUser"
        mock_message.author.discriminator = "1234"
        mock_message.author.id = "12345"
        mock_message.id = "67890"
        mock_message.channel.id = "channel123"
        mock_message.guild = Mock()
        mock_message.guild.id = "guild456"
        mock_message.content = "Check this file"
        mock_message.created_at.isoformat.return_value = "2023-01-01T12:00:00"
        
        # Create mock attachment
        mock_attachment = Mock(spec=Attachment)
        mock_attachment.id = "attach123"
        mock_attachment.filename = "test.png"
        mock_attachment.url = "https://example.com/test.png"
        mock_attachment.size = 1024
        mock_attachment.content_type = "image/png"
        
        mock_message.attachments = [mock_attachment]
        mock_message.embeds = []
        mock_message.mentions = []
        mock_message.role_mentions = []
        mock_message.channel_mentions = []
        mock_message.type = Mock()
        mock_message.type.name = "default"
        mock_message.pinned = False
        mock_message.reference = None
        mock_message.flags = Mock()
        
        # Set up flag behavior
        def getattr_side_effect(obj, name):
            if name == "suppress_embeds":
                return False
            raise AttributeError(f"'{type(obj).__name__}' object has no attribute '{name}'")
        
        mock_message.flags.__getattr__ = Mock(side_effect=getattr_side_effect)
        mock_message.flags.suppress_embeds = False
        
        # Set up mock to return file IDs for downloaded files
        self.mock_db.store_message_files.return_value = ["attach_file_id_123"]
        
        # Process the message
        await self.message_monitor.process_message(mock_message)
        
        # Verify attachments data in the stored message
        self.mock_db.store_message.assert_called_once()
        call_args = self.mock_db.store_message.call_args[0][0]
        
        attachments_data = json.loads(call_args['attachments'])
        self.assertEqual(len(attachments_data), 1)
        self.assertEqual(attachments_data[0]['id'], "attach123")
        self.assertEqual(attachments_data[0]['filename'], "test.png")
        self.assertEqual(attachments_data[0]['url'], "https://example.com/test.png")
        
        # Verify that store_message_files was called
        self.mock_db.store_message_files.assert_called_once()
    
    @patch('message_monitor.logger')
    async def test_process_message_with_embeds(self, mock_logger):
        """Test processing a message with embeds containing images"""
        # Create a mock message with embeds
        mock_message = AsyncMock()
        mock_message.author = Mock()
        mock_message.author.bot = False
        mock_message.author.name = "TestUser"
        mock_message.author.discriminator = "1234"
        mock_message.author.id = "12345"
        mock_message.id = "67890"
        mock_message.channel.id = "channel123"
        mock_message.guild = Mock()
        mock_message.guild.id = "guild456"
        mock_message.content = "Check this embed"
        mock_message.created_at.isoformat.return_value = "2023-01-01T12:00:00"
        mock_message.attachments = []
        
        # Create mock embed
        mock_embed = Mock(spec=Embed)
        mock_embed.image = Mock()
        mock_embed.image.url = "https://example.com/embed_image.jpg"
        mock_embed.thumbnail = Mock()
        mock_embed.thumbnail.url = "https://example.com/thumbnail.jpg"
        mock_embed.description = "Check this link: https://example.com/doc.pdf"
        
        # Create mock embed field
        mock_field = Mock()
        mock_field.name = "Field"
        mock_field.value = "Download: https://example.com/file.zip"
        mock_embed.fields = [mock_field]
        
        mock_message.embeds = [mock_embed]
        mock_message.mentions = []
        mock_message.role_mentions = []
        mock_message.channel_mentions = []
        mock_message.type = Mock()
        mock_message.type.name = "default"
        mock_message.pinned = False
        mock_message.reference = None
        mock_message.flags = Mock()
        
        # Set up flag behavior
        def getattr_side_effect(obj, name):
            if name == "suppress_embeds":
                return False
            raise AttributeError(f"'{type(obj).__name__}' object has no attribute '{name}'")
        
        mock_message.flags.__getattr__ = Mock(side_effect=getattr_side_effect)
        mock_message.flags.suppress_embeds = False
        
        # Process the message
        await self.message_monitor.process_message(mock_message)
        
        # Verify that download_url was called for embed images and URLs
        expected_calls = [
            call('https://example.com/embed_image.jpg', 'embed_image.jpg', '67890', 'channel123', 'guild456', '12345'),
            call('https://example.com/thumbnail.jpg', 'thumbnail.jpg', '67890', 'channel123', 'guild456', '12345'),
            call('https://example.com/doc.pdf', 'doc.pdf', '67890', 'channel123', 'guild456', '12345'),
            call('https://example.com/file.zip', 'file.zip', '67890', 'channel123', 'guild456', '12345')
        ]
        
        # Check that all expected calls were made (order doesn't matter)
        self.assertEqual(len(self.mock_db.download_url.call_args_list), len(expected_calls))
        for expected_call in expected_calls:
            self.assertIn(expected_call, self.mock_db.download_url.call_args_list)
    
    @patch('message_monitor.logger')
    async def test_extract_and_download_urls(self, mock_logger):
        """Test the _extract_and_download_urls method"""
        # Test text with URLs of different types
        test_text = (
            "Check these files:\n"
            "https://example.com/image.jpg\n"
            "https://example.com/document.pdf\n"
            "https://example.com/video.mp4\n"
            "https://example.com/plaintext.txt\n"  # Should be ignored
            "Not a URL: example.com/file.zip"  # Should be ignored
        )
        
        # Call the method
        result = await self.message_monitor._extract_and_download_urls(
            test_text, "msg123", "channel123", "guild456", "user789"
        )
        
        # Verify that download_url was called for the correct URLs
        expected_calls = [
            call('https://example.com/image.jpg', 'image.jpg', 'msg123', 'channel123', 'guild456', 'user789'),
            call('https://example.com/document.pdf', 'document.pdf', 'msg123', 'channel123', 'guild456', 'user789'),
            call('https://example.com/video.mp4', 'video.mp4', 'msg123', 'channel123', 'guild456', 'user789')
        ]
        
        # Check that all expected calls were made (order doesn't matter)
        self.assertEqual(len(self.mock_db.download_url.call_args_list), len(expected_calls))
        for expected_call in expected_calls:
            self.assertIn(expected_call, self.mock_db.download_url.call_args_list)
        
        # Verify the result contains the expected file IDs
        self.assertEqual(len(result), 3)
        for file_id in result:
            self.assertEqual(file_id, "file_id_123")

    @patch('message_monitor.logger')
    async def test_error_handling(self, mock_logger):
        """Test error handling in process_message"""
        # Create a mock message that will cause an error
        mock_message = AsyncMock()
        mock_message.author = Mock()
        mock_message.author.bot = False
        
        # Set up store_message to raise an exception
        self.mock_db.store_message.side_effect = Exception("Test error")
        
        # Process the message
        await self.message_monitor.process_message(mock_message)
        
        # Verify that the error was logged
        mock_logger.error.assert_called_once()
        self.assertIn("Error processing message", mock_logger.error.call_args[0][0])

if __name__ == '__main__':
    unittest.main()