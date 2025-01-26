
# Use the official Python image with a slim base for minimal size
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the project files into the container
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port (if necessary, for example if using webhooks)
EXPOSE 8080

# Run the bot
CMD ["python", "bot.py"]
