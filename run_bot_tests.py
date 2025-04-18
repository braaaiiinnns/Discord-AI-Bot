#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Runner script for Discord bot tests.
This script executes the test suite and displays the results in a readable format.
"""

import unittest
import sys
import time
import os
from datetime import datetime
from tests.test_discord_bot import TestDiscordBot, run_tests

def print_colored(text, color_code):
    """Print text in color"""
    print(f"\033[{color_code}m{text}\033[0m")

def print_green(text):
    """Print text in green"""
    print_colored(text, '92')

def print_red(text):
    """Print text in red"""
    print_colored(text, '91')

def print_yellow(text):
    """Print text in yellow"""
    print_colored(text, '93')

def print_blue(text):
    """Print text in blue"""
    print_colored(text, '94')

def print_header(text):
    """Print a header with decoration"""
    print("\n" + "=" * 80)
    print_blue(text)
    print("=" * 80)

def print_section(text):
    """Print a section header"""
    print("\n" + "-" * 40)
    print_yellow(text)
    print("-" * 40)

class TestResultCollector(unittest.TextTestResult):
    """Custom test result collector to provide better output"""
    
    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.successes = []
        self.start_time = None
        self.test_times = {}
        
    def startTest(self, test):
        self.start_time = time.time()
        super().startTest(test)
        
    def addSuccess(self, test):
        self.successes.append(test)
        elapsed = time.time() - self.start_time
        self.test_times[test.id()] = elapsed
        super().addSuccess(test)
        
    def addError(self, test, err):
        elapsed = time.time() - self.start_time
        self.test_times[test.id()] = elapsed
        super().addError(test, err)
        
    def addFailure(self, test, err):
        elapsed = time.time() - self.start_time
        self.test_times[test.id()] = elapsed
        super().addFailure(test, err)
        
    def addSkip(self, test, reason):
        self.test_times[test.id()] = 0
        super().addSkip(test, reason)

class TestRunner(unittest.TextTestRunner):
    """Custom test runner with better formatting"""
    
    def __init__(self, **kwargs):
        kwargs['resultclass'] = TestResultCollector
        super().__init__(**kwargs)
        
    def run(self, test):
        result = super().run(test)
        return result

def run_bot_tests():
    """Run the bot tests with prettier output"""
    print_header("Discord Bot Test Suite")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python version: {sys.version}")
    print()
    
    # Create a test suite with all tests
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestDiscordBot)
    
    # Run the tests with our custom runner
    runner = TestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print_header("Test Results Summary")
    print(f"Tests ran: {result.testsRun}")
    print(f"Time elapsed: {sum(result.test_times.values()):.2f} seconds")
    print()
    
    if result.wasSuccessful():
        print_green(f"SUCCESS! All {len(result.successes)} tests passed.")
    else:
        print_red(f"FAILED! {len(result.failures)} failures, {len(result.errors)} errors")
    
    # Print details of test cases
    print_section("Test Timings")
    for test_id, elapsed in sorted(result.test_times.items(), key=lambda x: x[1], reverse=True):
        test_name = test_id.split('.')[-1]
        print(f"{test_name:<50} {elapsed:.4f}s")
    
    # Print module verification results
    print_section("Module Verification Results")
    
    modules_to_check = [
        ("Bot Initialization", len([t for t in result.successes if "test_bot_initialization" in t.id()]) > 0),
        ("OpenAI Response", len([t for t in result.successes if "test_openai_response_generation" in t.id()]) > 0),
        ("Google GenAI Response", len([t for t in result.successes if "test_google_response_generation" in t.id()]) > 0),
        ("Claude Response", len([t for t in result.successes if "test_claude_response_generation" in t.id()]) > 0),
        ("Grok Response", len([t for t in result.successes if "test_grok_response_generation" in t.id()]) > 0),
        ("Response Summarization", len([t for t in result.successes if "test_long_response_summarization" in t.id()]) > 0),
        ("Response Channel Routing", len([t for t in result.successes if "test_response_channel_routing" in t.id()]) > 0),
        ("Error Handling", len([t for t in result.successes if "test_error_handling_in_ai_request" in t.id()]) > 0),
        ("AI Logging", len([t for t in result.successes if "test_ai_logging" in t.id()]) > 0),
    ]
    
    for module_name, success in modules_to_check:
        status = "✅ PASSED" if success else "❌ FAILED"
        color_func = print_green if success else print_red
        color_func(f"{module_name:<30} {status}")
    
    print("\n")
    return result.wasSuccessful()

if __name__ == "__main__":
    success = run_bot_tests()
    sys.exit(0 if success else 1)