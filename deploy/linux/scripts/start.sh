#!/bin/bash
set -e
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    echo "Error: .env file not found. Copy .env.example and fill in credentials."
    exit 1
fi

docker compose up -d
echo ""
echo "Stack started."
echo "  VNC:  localhost:5900"
echo "  API:  localhost:8000"
echo "  Live: localhost:4001"
echo "  Paper: localhost:4002"