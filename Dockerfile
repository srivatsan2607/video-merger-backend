# Use an official Python image as the base image
FROM python:3.8.10

# Install system dependencies (including Redis and FFmpeg)
RUN apt-get update && apt-get install -y \
    redis-server \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements.txt file into the container
COPY requirements.txt .

# Install Python dependencies from the requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project files into the container
COPY . .

# Expose port 5000 for the Python backend and 6379 for Redis
EXPOSE 5000 6379

# Run Redis server in the background and start the Python app
CMD redis-server --daemonize yes && python app.py
