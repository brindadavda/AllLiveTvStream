#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== HydraStream Dependency Installer ===${NC}"

# Check if brew is installed
if ! command -v brew &> /dev/null; then
    echo -e "${YELLOW}Homebrew not detected. Please install Homebrew from https://brew.sh first.${NC}"
    exit 1
fi

echo -e "${GREEN}Homebrew detected!${NC}"

# Install Redis
echo -e "${BLUE}1. Installing Redis via Homebrew...${NC}"
if brew list redis &>/dev/null; then
    echo -e "Redis is already installed."
else
    brew install redis
fi

# Install MongoDB
echo -e "${BLUE}2. Tapping MongoDB & Installing mongodb-community@6.0...${NC}"
if brew list mongodb-community@6.0 &>/dev/null; then
    echo -e "MongoDB community is already installed."
else
    # Tap mongodb/brew and install
    brew tap mongodb/brew || true
    brew install mongodb-community@6.0 || true
fi

# Start Services
echo -e "${BLUE}3. Starting database services...${NC}"
echo -e "Starting Redis..."
brew services restart redis || brew services start redis

echo -e "Starting MongoDB..."
brew services restart mongodb-community@6.0 || brew services start mongodb-community@6.0

echo -e "${GREEN}=== Dependency Setup Complete! ===${NC}"
echo -e "Redis and MongoDB are now running in the background as services."
echo -e "HydraStream backend will automatically switch from Fallback Mode to Production MongoDB and Redis."
