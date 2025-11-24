#!/bin/bash

# OpenDeploy Generic Deployment Script
# Deploys the current stack to any Linux server via SSH.
# Usage: ./deploy.sh <user>@<host> [api_key]

TARGET=$1
API_KEY=${2:-"secret-key-123"}

if [ -z "$TARGET" ]; then
    echo "Usage: ./deploy.sh <user>@<host> [api_key]"
    echo "Example: ./deploy.sh ubuntu@1.2.3.4 my-secure-key"
    exit 1
fi

echo "🚀 Deploying OpenDeploy to $TARGET..."

# 1. Copy files to remote server
echo "📦 Syncing files..."
# We use rsync to copy everything except what's in .dockerignore or git
rsync -avz --exclude-from='.dockerignore' \
    --exclude '.git' \
    --exclude 'venv' \
    --exclude '.venv' \
    . $TARGET:~/opendeploy/

# 2. Run setup on remote server
echo "🔧 Configuring remote server..."
ssh -t $TARGET "bash -s" << EOF
    set -e

    # Install Docker if not present
    if ! command -v docker &> /dev/null; then
        echo "Installing Docker..."
        curl -fsSL https://get.docker.com -o get-docker.sh
        sudo sh get-docker.sh
        rm get-docker.sh
    fi

    # Go to directory
    cd ~/opendeploy

    # Create .env file for secrets
    echo "OPENDEPLOY_API_KEY=$API_KEY" > .env

    # Start services
    echo "🚀 Starting services..."
    # We use 'docker compose' (v2) or 'docker-compose' (v1)
    if command -v docker-compose &> /dev/null; then
        sudo docker-compose down || true
        sudo docker-compose up -d --build
    else
        sudo docker compose down || true
        sudo docker compose up -d --build
    fi

    # Get Public IP (naive check)
    PUBLIC_IP=\$(curl -s ifconfig.me || echo "localhost")

    echo "---------------------------------------------------"
    echo "✅ Deployment Complete!"
    echo "---------------------------------------------------"
    echo "🌍 UI:  http://\$PUBLIC_IP:3000"
    echo "🔌 API: http://\$PUBLIC_IP:8000"
    echo "🔑 Key: $API_KEY"
    echo "---------------------------------------------------"
EOF
