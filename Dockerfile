# Use a lightweight Python image
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Install Poetry
RUN pip install --no-cache-dir poetry

# Copy the project files to the working directory
COPY . .

# Install dependencies using Poetry
RUN poetry install --no-root

# Command to run your script
CMD ["poetry", "run", "python", "chatgpt_discord_bot_v4.1.py"]
