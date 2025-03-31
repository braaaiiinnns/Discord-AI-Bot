import json
import random

def get_random_emoji():
    # Load the JSON file
    with open('ascii_emoji.json', 'r') as file:
        emoji_data = json.load(file)
    
    # Randomly select a value from the dictionary (which represents the emoji)
    random_emoji = random.choice(list(emoji_data.values()))
    
    return random_emoji
