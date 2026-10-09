#!/usr/bin/env bash
set -e

echo "=== Autonomous Crypto Scalping Agent Deployment ==="

# Check for .env file
if [ ! -f ".env" ]; then
    echo "Warning: .env file not found. Copying .env.example to .env..."
    cp .env.example .env
fi

# Ensure storage directories exist
mkdir -p storage/trades storage/signals storage/logs

echo "1. Building Docker container..."
docker compose build

echo "2. Running test suite inside container before deployment..."
docker compose run --rm autonomous-scalper pytest tests/ -v

echo "3. Starting services in background..."
docker compose up -d

echo "4. Checking service health..."
sleep 5
docker compose ps

echo "Deployment completed successfully! Dashboard available at http://localhost:8000"
