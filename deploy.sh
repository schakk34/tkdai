#!/bin/bash

# Deployment script for TKD AI application

set -e  # Exit on any error

echo "🚀 Starting TKD AI deployment..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

# Stop existing containers
echo "🛑 Stopping existing containers..."
docker-compose down --remove-orphans

# Remove old images to ensure fresh build
echo "🧹 Cleaning up old images..."
docker system prune -f

# Build the new image
echo "🔨 Building Docker image..."
docker-compose build --no-cache

# Start the application
echo "🚀 Starting application..."
docker-compose up -d

# Wait for the application to be ready
echo "⏳ Waiting for application to start..."
sleep 10

# Check if the application is running
echo "🔍 Checking application health..."
for i in {1..30}; do
    if curl -f http://localhost:5002/ > /dev/null 2>&1; then
        echo "✅ Application is running successfully!"
        echo "🌐 Access your application at: http://localhost:5002"
        exit 0
    fi
    echo "⏳ Waiting for application to be ready... (attempt $i/30)"
    sleep 2
done

echo "❌ Application failed to start properly. Check logs with: docker-compose logs"
docker-compose logs
exit 1 