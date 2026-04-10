FROM python:3.11-slim

WORKDIR /app

# Install test app deps
COPY test_app/requirements.txt /app/test_app/requirements.txt
RUN pip install --no-cache-dir -r /app/test_app/requirements.txt

# Copy backend (for SDK) and test app
COPY backend/ /app/backend/
COPY test_app/ /app/test_app/

# Install backend SDK deps
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

EXPOSE 8501

CMD ["streamlit", "run", "/app/test_app/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
