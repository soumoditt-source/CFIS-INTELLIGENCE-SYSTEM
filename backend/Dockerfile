FROM python:3.11-slim

# AegisCX Backend Dockerfile
# Includes FFmpeg for audio processing

LABEL maintainer="AegisCX Engineering"
LABEL version="1.0"

# Install system dependencies including FFmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    libgomp1 \
    build-essential \
    git \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies first (Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p data/raw data/processed data/chromadb logs

# Non-root user for security
RUN useradd -m -u 1000 aegiscx && chown -R aegiscx:aegiscx /app
USER aegiscx

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
