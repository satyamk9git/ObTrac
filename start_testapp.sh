#!/bin/bash
# Start ObTrac Test App (Streamlit)

echo "=== Starting ObTrac Test App ==="

# Install deps
pip install -r test_app/requirements.txt -q
pip install -r backend/requirements.txt -q

# Start Streamlit
echo "Starting Streamlit on http://localhost:8501"
streamlit run test_app/app.py --server.port 8501
