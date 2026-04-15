#!/bin/bash
# Start ObTrac Test App

echo "=== ObTrac Test App ==="

# Install deps
echo "Installing dependencies..."
pip install -r test_app/requirements.txt -q

# Register prompts in the registry (safe to run multiple times)
echo "Setting up prompts in registry..."
python -m test_app.prompts_setup

# Start Streamlit
echo ""
echo "Starting app on http://localhost:8501"
python -m streamlit run test_app/streamlit_main_app.py --server.port 8501
