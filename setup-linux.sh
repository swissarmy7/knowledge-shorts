#!/bin/bash

# Knowledge Shorts - Linux Setup Script (Ubuntu/Debian)
# This script automates the installation of Python, Node.js, and FFmpeg for the Shorts Generator.

set -e

echo "🚀 Starting Knowledge Shorts environment setup..."

# 1. Update and install base packages
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv ffmpeg git curl libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2 libpango-1.0-0 libpangocairo-1.0-0

# 2. Install Node.js (v20) via NVM if not present
if ! command -v node &> /dev/null; then
    echo "🟢 Installing Node.js (LTS)..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt install -y nodejs
fi

# 3. Setup Python Virtual Environment
echo "🐍 Setting up Python Virtual Environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip
if [ -f "backend/requirements.txt" ]; then
    pip install -r backend/requirements.txt
else
    echo "⚠️ Warning: backend/requirements.txt not found!"
fi

# 4. Setup Node.js dependencies for Video Engine
echo "🎬 Setting up Video Engine (Remotion)..."
if [ -d "video-engine" ]; then
    cd video-engine
    npm install
    # Ensure Playwright/Chromium dependencies for Remotion
    npx remotion browser ensure
    cd ..
else
    echo "⚠️ Warning: video-engine directory not found!"
fi

# 5. Process Manager (PM2)
if ! command -v pm2 &> /dev/null; then
    echo "🛠️ Installing PM2 process manager..."
    sudo npm install -g pm2
fi

echo "✅ Setup complete!"
echo "--------------------------------------------------"
echo "To start the backend:"
echo "pm2 start \"source .venv/bin/activate && uvicorn backend.main:app --host 0.0.0.0 --port 8000\" --name shorts-backend"
echo ""
echo "To monitor logs: pm2 logs"
echo "--------------------------------------------------"
