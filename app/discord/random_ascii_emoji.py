import json
import random
import os
from config.config import ASCII_EMOJI_FILE

class RandomAsciiEmoji:
    def __init__(self, logger):
        self.logger = logger
        self.emoji_file = ASCII_EMOJI_FILE
        self.emotions = {}
        self.load_emoji()

    def load_emoji(self):
        # Load the JSON file
        try:
            with open(self.emoji_file, 'r') as file:
                self.emotions = json.load(file)
            self.logger.info(f"Successfully loaded ASCII emoji from {self.emoji_file}")
        except FileNotFoundError:
            self.logger.warning(f"ASCII emoji file not found at {self.emoji_file}. Using fallback emojis.")
            # Provide fallback emojis if file isn't found
            self.emotions = {
                "happy": "(^‿^)",
                "sad": "(╥﹏╥)",
                "love": "(♥‿♥)",
                "cool": "(⌐■_■)",
                "shrug": "¯\\_(ツ)_/¯",
                "tableflip": "(╯°□°）╯︵ ┻━┻",
                "smile": "ʘ‿ʘ",
                "wave": "(•◡•)/",
                "thinking": "(⊙_⊙)",
                "wink": "(^_-)"
            }
        except json.JSONDecodeError:
            self.logger.error(f"Error parsing JSON from {self.emoji_file}. Using fallback emojis.")
            # Provide fallback emojis if file is corrupted
            self.emotions = {
                "happy": "(^‿^)",
                "sad": "(╥﹏╥)"
            }

    def get_random_emoji(self):
        # Randomly select a value from the dictionary (which represents the emoji)
        if not self.emotions:
            return "(・_・)"  # Default emoji if emotions dict is empty
        random_emoji = random.choice(list(self.emotions.values()))
        return random_emoji
