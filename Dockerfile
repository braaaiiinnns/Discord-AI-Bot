FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Install system dependencies required for cryptography and other libraries
RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy the project files
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Explicitly install pytz to ensure it's available
RUN pip install --no-cache-dir pytz

# Create directories for data persistence
RUN mkdir -p /app/data/db /app/data/files /app/data/static /app/data/flask_session /app/logs && \
    chmod -R 755 /app/data /app/logs

# Ensure the static files are copied to the correct locations
# These will be available for container initialization (first run before volume mounts)
COPY data/static/ascii_emoji.json /app/data/static/
COPY data/static/ascii_emoji.json data/static/task_examples.json /app/data/static/

# Run the bot
CMD ["python", "main.py"]