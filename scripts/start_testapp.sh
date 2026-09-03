#!/bin/bash
# Start ObTrac Test App

echo "=== ObTrac Test App ==="

# Install deps
echo "Installing dependencies..."
pip install -r demos/langgraph_streamlit_rag/requirements.txt -q

# Register prompts in the registry (safe to run multiple times)
echo "Setting up prompts in registry..."
python -m demos.langgraph_streamlit_rag.prompts_setup

# Start Streamlit
echo ""
echo "Starting app on http://localhost:8501"
python -m streamlit run demos/langgraph_streamlit_rag/streamlit_main_app.py --server.port 8501
