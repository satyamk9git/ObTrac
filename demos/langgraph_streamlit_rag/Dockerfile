FROM python:3.11-slim

WORKDIR /app

# Install test app deps
COPY demos/langgraph_streamlit_rag/requirements.txt /app/demos/langgraph_streamlit_rag/requirements.txt
RUN pip install --no-cache-dir -r /app/demos/langgraph_streamlit_rag/requirements.txt

# Copy backend (for SDK) and demos (langgraph_streamlit_rag imports sibling
# demos.simple_multi_tool_agent, so the whole demos/ tree is needed, not just
# this one demo's folder)
COPY backend/ /app/backend/
COPY demos/ /app/demos/

# Install backend SDK deps
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

EXPOSE 8501

CMD ["streamlit", "run", "/app/demos/langgraph_streamlit_rag/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
