#!/bin/bash

# Setup script for forms-backend

echo "Creating virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Preparing log directory..."
mkdir -p logs

echo "Environment setup complete."
echo "You can now run the app with: python app.py"
echo "Or run celery with: celery -A config.celery worker --loglevel=info"
