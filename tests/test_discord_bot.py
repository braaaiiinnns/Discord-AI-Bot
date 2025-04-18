#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test file for Discord bot functionality.
Tests the core functionality of the bot, including LLM interactions and response routing.
"""

import unittest
import asyncio
import logging
import json
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch, Mock
from datetime import datetime

# Add the parent directory to sys.path to import the app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.discord.bot import DiscordBot
from app.discord.cogs.gen_ai_cog import AICogCommands
from app.discord.state import BotState
from utils.ai_services import OpenAIStrategy, GoogleGenAIStrategy, ClaudeStrategy, GrokStrategy
from utils.utilities import route_response
from config.config import DEFAULT_SUMMARY_LIMIT

# Configure logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('test_discord_bot')

class TestDiscordBot(unittest.TestCase):
    """Test case for Discord bot functionality"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment once for all test methods"""
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
    
    @classmethod
    def tearDownClass(cls):
        """Clean up resources after all tests"""
        cls.loop.close()
    
    def setUp(self):
        """Set up test fixtures before each test method"""
        # Create mocks for Discord client and dependencies
        self.mock_client = MagicMock()
        self.mock_client.user = MagicMock()
        self.mock_client.user.name = "TestBot"
        self.mock_client.user.id = 12345
        self.mock_client.guilds = []
        self.mock_client.tree = MagicMock()
        self.mock_client.tree.sync = AsyncMock()
        self.mock_client.tree.add_command = MagicMock()
        self.mock_client.add_cog = AsyncMock()
        
        # Mock logger for testing
        self.mock_logger = MagicMock()
        
        # Mock AI clients
        self.mock_openai_client = MagicMock()
        self.mock_google_client = MagicMock()
        self.mock_claude_client = MagicMock()
        self.mock_grok_client = MagicMock()
        
        # Set up bot state
        self.bot_state = BotState(timeout=3600)
        
        # Mock response channels
        self.response_channels = {}
        
        # Create a test guild and channel
        self.test_guild = MagicMock()
        self.test_guild.id = 98765
        self.test_guild.name = "Test Server"
        
        self.test_channel = MagicMock()
        self.test_channel.id = 54321
        self.test_channel.name = "test-channel"
        
        self.response_channel = MagicMock()
        self.response_channel.id = 11111
        self.response_channel.name = "🤖"
        self.response_channel.send = AsyncMock()
        
        self.response_channels[self.test_guild.id] = self.response_channel
        
        # Create a test user
        self.test_user = MagicMock()
        self.test_user.id = 76543
        self.test_user.name = "TestUser"
        self.test_user.discriminator = "1234"
        
        # Create a mock interaction
        self.mock_interaction = AsyncMock()
        self.mock_interaction.user = self.test_user
        self.mock_interaction.guild = self.test_guild
        self.mock_interaction.channel = self.test_channel
        self.mock_interaction.channel_id = self.test_channel.id
        self.mock_interaction.response = AsyncMock()
        self.mock_interaction.followup = AsyncMock()
        self.mock_interaction.response.defer = AsyncMock()
        self.mock_interaction.followup.send = AsyncMock()
        
    def tearDown(self):
        """Clean up fixtures after each test method"""
        # Reset any mock responses
        if hasattr(self, 'mock_interaction'):
            self.mock_interaction.reset_mock()

    async def async_test(self, coroutine):
        """Helper to run async test coroutines"""
        return await coroutine
    
    def test_bot_initialization(self):
        """Test Discord bot initialization"""
        # Create patch for necessary imports
        with patch('app.discord.bot.setup_logger', return_value=self.mock_logger), \
             patch('app.discord.bot.commands.Bot', return_value=self.mock_client), \
             patch('app.discord.bot.get_openai_client', return_value=self.mock_openai_client), \
             patch('app.discord.bot.get_google_genai_client', return_value=self.mock_google_client), \
             patch('app.discord.bot.get_claude_client', return_value=self.mock_claude_client), \
             patch('app.discord.bot.get_grok_client', return_value=self.mock_grok_client), \
             patch('app.discord.bot.MessageMonitor'), \
             patch('app.discord.bot.AIInteractionLogger'), \
             patch('app.discord.bot.TaskScheduler'), \
             patch('app.discord.bot.TaskManager'), \
             patch('app.discord.bot.RoleColorManager'):
            
            # Initialize the bot
            bot = DiscordBot()
            
            # Verify logger and client initialization
            self.assertIsNotNone(bot.logger)
            self.assertIsNotNone(bot.client)
            self.assertIsNotNone(bot.bot_state)
            self.assertEqual({}, bot.response_channels)
            
            # Verify AI clients initialization
            self.assertEqual(self.mock_openai_client, bot.openai_client)
            self.assertEqual(self.mock_google_client, bot.google_client)
            self.assertEqual(self.mock_claude_client, bot.claude_client)
            self.assertEqual(self.mock_grok_client, bot.grok_client)
            
            self.mock_logger.info.assert_called_with("AI clients initialized")
    
    @patch('app.discord.cogs.gen_ai_cog.route_response')
    async def test_openai_response_generation(self, mock_route_response):
        """Test that OpenAI responses are generated and routed correctly"""
        # Create AI cog
        ai_cog = AICogCommands(
            self.mock_client,
            self.bot_state,
            self.response_channels,
            self.mock_logger
        )
        
        # Setup clients
        mock_openai_strategy = AsyncMock(spec=OpenAIStrategy)
        sample_response = "This is a test response from the OpenAI model."
        mock_openai_strategy.generate_response.return_value = sample_response
        
        with patch('app.discord.cogs.gen_ai_cog.OpenAIStrategy', return_value=mock_openai_strategy):
            ai_cog.setup_clients(
                self.mock_openai_client, 
                self.mock_google_client, 
                self.mock_claude_client, 
                self.mock_grok_client
            )
            
            # Call the AI request handler with GPT model
            prompt = "What is the meaning of life?"
            await ai_cog._handle_ai_request(
                self.mock_interaction,
                prompt,
                mock_openai_strategy,
                "GPT-4o-mini",
                "You are a helpful assistant."
            )
            
            # Verify the response generation
            mock_openai_strategy.generate_response.assert_called_once()
            
            # Verify the response routing
            mock_route_response.assert_called_once()
            args = mock_route_response.call_args[0]
            self.assertEqual(args[0], self.mock_interaction)
            self.assertEqual(args[1], prompt)
            self.assertEqual(args[2], sample_response)
            self.assertIsNone(args[3])  # No summary needed (response is short)
            self.assertEqual(args[4], self.response_channels)
    
    @patch('app.discord.cogs.gen_ai_cog.route_response')
    async def test_google_response_generation(self, mock_route_response):
        """Test that Google GenAI responses are generated and routed correctly"""
        # Create AI cog
        ai_cog = AICogCommands(
            self.mock_client,
            self.bot_state,
            self.response_channels,
            self.mock_logger
        )
        
        # Setup clients
        mock_google_strategy = AsyncMock(spec=GoogleGenAIStrategy)
        sample_response = "This is a test response from the Google GenAI model."
        mock_google_strategy.generate_response.return_value = sample_response
        
        with patch('app.discord.cogs.gen_ai_cog.GoogleGenAIStrategy', return_value=mock_google_strategy):
            ai_cog.setup_clients(
                self.mock_openai_client, 
                self.mock_google_client, 
                self.mock_claude_client, 
                self.mock_grok_client
            )
            
            # Call the AI request handler with Google model
            prompt = "Tell me about machine learning"
            await ai_cog._handle_ai_request(
                self.mock_interaction,
                prompt,
                mock_google_strategy,
                "Google GenAI",
                "You are a helpful assistant."
            )
            
            # Verify the response generation
            mock_google_strategy.generate_response.assert_called_once()
            
            # Verify the response routing
            mock_route_response.assert_called_once()
            args = mock_route_response.call_args[0]
            self.assertEqual(args[0], self.mock_interaction)
            self.assertEqual(args[1], prompt)
            self.assertEqual(args[2], sample_response)
            self.assertIsNone(args[3])  # No summary needed (response is short)
            self.assertEqual(args[4], self.response_channels)
    
    @patch('app.discord.cogs.gen_ai_cog.route_response')
    async def test_claude_response_generation(self, mock_route_response):
        """Test that Claude responses are generated and routed correctly"""
        # Create AI cog
        ai_cog = AICogCommands(
            self.mock_client,
            self.bot_state,
            self.response_channels,
            self.mock_logger
        )
        
        # Setup clients
        mock_claude_strategy = AsyncMock(spec=ClaudeStrategy)
        sample_response = "This is a test response from the Claude model, presented poetically."
        mock_claude_strategy.generate_response.return_value = sample_response
        
        with patch('app.discord.cogs.gen_ai_cog.ClaudeStrategy', return_value=mock_claude_strategy):
            ai_cog.setup_clients(
                self.mock_openai_client, 
                self.mock_google_client, 
                self.mock_claude_client, 
                self.mock_grok_client
            )
            
            # Call the AI request handler with Claude model
            prompt = "Write a poem about AI"
            await ai_cog._handle_ai_request(
                self.mock_interaction,
                prompt,
                mock_claude_strategy,
                "Claude",
                "You are a poetic assistant."
            )
            
            # Verify the response generation
            mock_claude_strategy.generate_response.assert_called_once()
            
            # Verify the response routing
            mock_route_response.assert_called_once()
            args = mock_route_response.call_args[0]
            self.assertEqual(args[0], self.mock_interaction)
            self.assertEqual(args[1], prompt)
            self.assertEqual(args[2], sample_response)
            self.assertIsNone(args[3])  # No summary needed (response is short)
            self.assertEqual(args[4], self.response_channels)
    
    @patch('app.discord.cogs.gen_ai_cog.route_response')
    async def test_grok_response_generation(self, mock_route_response):
        """Test that Grok responses are generated and routed correctly"""
        # Create AI cog
        ai_cog = AICogCommands(
            self.mock_client,
            self.bot_state,
            self.response_channels,
            self.mock_logger
        )
        
        # Setup clients
        mock_grok_strategy = AsyncMock(spec=GrokStrategy)
        sample_response = "This is a witty test response from the Grok model."
        mock_grok_strategy.generate_response.return_value = sample_response
        
        with patch('app.discord.cogs.gen_ai_cog.GrokStrategy', return_value=mock_grok_strategy):
            ai_cog.setup_clients(
                self.mock_openai_client, 
                self.mock_google_client, 
                self.mock_claude_client, 
                self.mock_grok_client
            )
            
            # Call the AI request handler with Grok model
            prompt = "Tell me a joke about AI"
            await ai_cog._handle_ai_request(
                self.mock_interaction,
                prompt,
                mock_grok_strategy,
                "Grok",
                "You are a witty assistant."
            )
            
            # Verify the response generation
            mock_grok_strategy.generate_response.assert_called_once()
            
            # Verify the response routing
            mock_route_response.assert_called_once()
            args = mock_route_response.call_args[0]
            self.assertEqual(args[0], self.mock_interaction)
            self.assertEqual(args[1], prompt)
            self.assertEqual(args[2], sample_response)
            self.assertIsNone(args[3])  # No summary needed (response is short)
            self.assertEqual(args[4], self.response_channels)
    
    @patch('app.discord.cogs.gen_ai_cog.route_response')  
    async def test_long_response_summarization(self, mock_route_response):
        """Test that long responses are properly summarized"""
        # Create AI cog
        ai_cog = AICogCommands(
            self.mock_client,
            self.bot_state,
            self.response_channels,
            self.mock_logger
        )
        
        # Create a long response that exceeds the summary limit
        long_response = "This is a very long response " * 200  # Will exceed DEFAULT_SUMMARY_LIMIT
        summary = "This is a summarized version of the long response"
        
        # Setup clients and strategies
        mock_openai_strategy = AsyncMock(spec=OpenAIStrategy)
        mock_openai_strategy.generate_response.return_value = long_response
        
        mock_google_strategy = AsyncMock(spec=GoogleGenAIStrategy)
        mock_google_strategy.generate_response.return_value = summary
        
        with patch('app.discord.cogs.gen_ai_cog.OpenAIStrategy', return_value=mock_openai_strategy), \
             patch('app.discord.cogs.gen_ai_cog.GoogleGenAIStrategy', return_value=mock_google_strategy):
            
            ai_cog.setup_clients(
                self.mock_openai_client, 
                self.mock_google_client, 
                self.mock_claude_client, 
                self.mock_grok_client
            )
            
            # Call the AI request handler
            prompt = "Give me a detailed explanation of quantum computing"
            await ai_cog._handle_ai_request(
                self.mock_interaction,
                prompt,
                mock_openai_strategy,
                "GPT-4o-mini",
                "You are a helpful assistant."
            )
            
            # Verify summarization occurred
            mock_google_strategy.generate_response.assert_called_once()
            
            # Verify response routing with summary
            mock_route_response.assert_called_once()
            args = mock_route_response.call_args[0]
            self.assertEqual(args[0], self.mock_interaction)
            self.assertEqual(args[1], prompt)
            self.assertEqual(args[2], long_response)
            self.assertEqual(args[3], summary)  # Summary should be provided
            self.assertEqual(args[4], self.response_channels)
    
    @patch('utils.utilities.get_random_emoji', return_value="😀")
    async def test_response_channel_routing(self, mock_get_emoji):
        """Test that responses are properly sent to response channels"""
        # Create a mock interaction and response channel
        interaction = self.mock_interaction
        
        # Define test data
        prompt = "Test prompt"
        response = "This is the full response"
        summary = "This is a summary"
        
        # Call route_response directly
        await self.async_test(route_response(
            interaction,
            prompt,
            response,
            summary,
            self.response_channels,
            self.mock_logger
        ))
        
        # Check that summary was sent to the user
        interaction.followup.send.assert_called_once_with(f"✉️: {prompt}\n📫: {summary}")
        
        # Check that full response was sent to the response channel
        self.response_channel.send.assert_called_once()
        sent_message = self.response_channel.send.call_args[0][0]
        self.assertIn(prompt, sent_message)
        self.assertIn(response, sent_message)
        self.assertIn("😀", sent_message)  # Check for emoji
    
    @patch('app.discord.cogs.gen_ai_cog.GoogleGenAIStrategy')
    async def test_summarization_fallback(self, mock_google_strategy_class):
        """Test fallback behavior when summarization fails"""
        # Create AI cog
        ai_cog = AICogCommands(
            self.mock_client,
            self.bot_state,
            self.response_channels,
            self.mock_logger
        )
        
        # Create a mock Google strategy that raises an exception
        mock_google_strategy = AsyncMock()
        mock_google_strategy.generate_response.side_effect = Exception("API error")
        mock_google_strategy_class.return_value = mock_google_strategy
        
        # Setup clients
        ai_cog.setup_clients(
            self.mock_openai_client, 
            self.mock_google_client, 
            self.mock_claude_client, 
            self.mock_grok_client
        )
        
        # Create a long response to summarize
        long_response = "This is a test response " * 100
        
        # Call summarize_response
        summary = await ai_cog._summarize_response(long_response)
        
        # Verify the fallback truncation was applied
        self.assertTrue(summary.endswith("... (truncated)"))
        self.assertEqual(len(summary), DEFAULT_SUMMARY_LIMIT + len("... (truncated)"))
    
    @patch('app.discord.cogs.gen_ai_cog.route_response')
    async def test_error_handling_in_ai_request(self, mock_route_response):
        """Test error handling when AI request fails"""
        # Create AI cog
        ai_cog = AICogCommands(
            self.mock_client,
            self.bot_state,
            self.response_channels,
            self.mock_logger
        )
        
        # Setup clients with a failing strategy
        mock_openai_strategy = AsyncMock(spec=OpenAIStrategy)
        mock_openai_strategy.generate_response.side_effect = Exception("API failure")
        
        ai_cog.setup_clients(
            self.mock_openai_client, 
            self.mock_google_client, 
            self.mock_claude_client, 
            self.mock_grok_client
        )
        
        # Call the AI request handler
        prompt = "This should fail"
        await ai_cog._handle_ai_request(
            self.mock_interaction,
            prompt,
            mock_openai_strategy,
            "GPT-4o-mini",
            "You are a helpful assistant."
        )
        
        # Verify error handling
        self.mock_logger.error.assert_called_once()
        self.mock_interaction.followup.send.assert_called_once_with(
            "An error occurred while processing your request. Please try again later."
        )
        
        # Verify route_response was not called
        mock_route_response.assert_not_called()
    
    async def test_ai_logging(self):
        """Test that AI interactions are properly logged"""
        # Create mock AI logger
        mock_ai_logger = AsyncMock()
        mock_ai_logger.log_interaction = AsyncMock()
        
        # Create AI cog with the mock logger
        ai_cog = AICogCommands(
            self.mock_client,
            self.bot_state,
            self.response_channels,
            self.mock_logger,
            mock_ai_logger
        )
        
        # Setup clients
        mock_openai_strategy = AsyncMock(spec=OpenAIStrategy)
        sample_response = "This is a test response."
        mock_openai_strategy.generate_response.return_value = sample_response
        
        with patch('app.discord.cogs.gen_ai_cog.route_response'):
            ai_cog.setup_clients(
                self.mock_openai_client, 
                self.mock_google_client, 
                self.mock_claude_client, 
                self.mock_grok_client
            )
            
            # Call the AI request handler
            prompt = "Test logging"
            model_name = "GPT-4o-mini"
            system_prompt = "You are a helpful assistant."
            
            await ai_cog._handle_ai_request(
                self.mock_interaction,
                prompt,
                mock_openai_strategy,
                model_name,
                system_prompt
            )
            
            # Verify logging occurred
            mock_ai_logger.log_interaction.assert_called_once()
            args = mock_ai_logger.log_interaction.call_args[1]
            self.assertEqual(args["user_id"], str(self.test_user.id))
            self.assertEqual(args["guild_id"], self.test_guild.id)
            self.assertEqual(args["channel_id"], self.test_channel.id)
            self.assertEqual(args["model"], model_name)
            self.assertEqual(args["prompt"], prompt)
            self.assertEqual(args["response"], sample_response)
            self.assertIn("execution_time", args)
            self.assertIn("metadata", args)
            self.assertEqual(args["metadata"]["system_prompt"], system_prompt)

def run_tests():
    """Run the tests"""
    unittest.main(argv=['first-arg-is-ignored'], exit=False)

if __name__ == '__main__':
    print("=" * 80)
    print("Discord Bot Test Suite")
    print(f"Running tests at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    unittest.main()