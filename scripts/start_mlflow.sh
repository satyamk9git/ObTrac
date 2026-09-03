#!/bin/bash
# Start MLflow Tracking Server

echo "=== Starting MLflow Tracking Server ==="

pip install mlflow -q

mkdir -p data/mlflow

echo "Starting MLflow on http://localhost:5000"
mlflow server \
    --host 0.0.0.0 \
    --port 5000 \
    --backend-store-uri sqlite:///data/mlflow/mlflow.db \
    --default-artifact-root ./data/mlflow/artifacts
