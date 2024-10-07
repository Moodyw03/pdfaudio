# Use an official Python image as a base
FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

# Set working directory in the container
WORKDIR /app

# Copy the requirements.txt file
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code to the container
COPY . /app/

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Start the app using gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:$PORT", "app:app"]
