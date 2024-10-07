# Use the official Python image from the Docker Hub
FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED 1

# Install system dependencies
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

# Create a working directory
WORKDIR /app

# Copy the requirements file to the container
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app's code into the container
COPY . /app/

# Specify the command to run the application
CMD ["gunicorn", "-b", "0.0.0.0:$PORT", "app:app"]
