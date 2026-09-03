#!/bin/bash
# Start ObTrac Backend

echo "=== Starting ObTrac Backend ==="

cd backend

# Create virtual env if not exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python -m venv venv
fi

# Activate venv
source venv/bin/activate 2>/dev/null || source venv/Scripts/activate 2>/dev/null

# Install deps
echo "Installing dependencies..."
pip install -r requirements.txt -q

# Create data directory
mkdir -p data/uploads

# Start server
echo "Starting FastAPI server on http://localhost:8000"
echo "API docs: http://localhost:8000/docs"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
