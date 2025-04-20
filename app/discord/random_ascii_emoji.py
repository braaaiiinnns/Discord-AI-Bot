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
        with open(self.emoji_file, 'r') as file:
            self.emotions = json.load(file)

    def get_random_emoji(self):
        # Randomly select a value from the dictionary (which represents the emoji)
        random_emoji = random.choice(list(self.emotions.values()))
        return random_emoji
