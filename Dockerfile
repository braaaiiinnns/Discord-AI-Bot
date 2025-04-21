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

# Create entrypoint script to copy files when container starts
RUN echo '#!/bin/bash\n\
# Copy static files to volume if the directory is empty\n\
if [ -d "/app/data/static" ] && [ -z "$(ls -A /app/data/static 2>/dev/null)" ]; then\n\
  echo "Copying static files to volume..."\n\
  cp -r /app/data_init/static/* /app/data/static/ 2>/dev/null || true\n\
fi\n\
\n\
# Copy other data directories if they exist and are empty\n\
if [ -d "/app/data/db" ] && [ -z "$(ls -A /app/data/db 2>/dev/null)" ]; then\n\
  echo "Copying database files to volume..."\n\
  cp -r /app/data_init/db/* /app/data/db/ 2>/dev/null || true\n\
fi\n\
\n\
if [ -d "/app/data/files" ] && [ -z "$(ls -A /app/data/files 2>/dev/null)" ]; then\n\
  echo "Copying files to volume..."\n\
  cp -r /app/data_init/files/* /app/data/files/ 2>/dev/null || true\n\
fi\n\
\n\
if [ -d "/app/data/flask_session" ] && [ -z "$(ls -A /app/data/flask_session 2>/dev/null)" ]; then\n\
  echo "Copying flask session files to volume..."\n\
  cp -r /app/data_init/flask_session/* /app/data/flask_session/ 2>/dev/null || true\n\
fi\n\
\n\
# Start the main application\n\
exec "$@"' > /app/entrypoint.sh

# Make entrypoint script executable
RUN chmod +x /app/entrypoint.sh

# Create backup of initial data
RUN mkdir -p /app/data_init && \
    cp -r /app/data/* /app/data_init/ 2>/dev/null || true

# Set the entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# Run the bot
CMD ["python", "main.py"]