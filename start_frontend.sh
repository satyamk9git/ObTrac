#!/bin/bash
# Start ObTrac Frontend

echo "=== Starting ObTrac Frontend ==="

cd frontend

# Install deps
if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
fi

# Start dev server
echo "Starting Next.js on http://localhost:3000"
npm run dev
