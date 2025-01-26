
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_or_create_assistant(mode, instructions=None):
    pass

async def process_assistant_response(assistant, message_content):
    pass
