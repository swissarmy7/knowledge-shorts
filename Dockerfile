# Knowledge Shorts - Dockerfile
# Multi-stage build for Python + Node.js (Remotion)

FROM node:20-slim AS base

# Install Python and FFmpeg
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv \
    ffmpeg \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxrandr2 libgbm1 libasound2 libpango-1.0-0 libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# 1. Install Backend Dependencies (Python)
COPY backend/requirements.txt ./backend/
RUN pip3 install --no-cache-dir -r backend/requirements.txt --break-system-packages

# 2. Install Video Engine Dependencies (Node.js)
COPY video-engine/package*.json ./video-engine/
RUN cd video-engine && npm install && npx remotion browser ensure

# 3. Copy source code
COPY . .

# 4. Final configuration
EXPOSE 8000

# Set environment variables for Puppeteer (headless)
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV REMOTION_CONCURRENCY=4

# Run backend
CMD ["python3", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
