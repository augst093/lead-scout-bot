FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Create a persistent volume mount point for the SQLite database
RUN mkdir -p /data

# Run the bot
CMD ["python", "bot.py"]
