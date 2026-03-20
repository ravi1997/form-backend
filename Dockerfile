# Use the full Python image which includes build tools (gcc, make, etc.) by default.
# This avoids the need to run apt-get update/install for build-essential, 
# which was failing due to network/DNS issues in the slim image.
FROM python:3.10-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Set work directory
WORKDIR /app

# No need for apt-get install build-essential/python3-dev as they are 
# already included in the full python:3.10-bookworm image.
# This bypasses failing apt-get update calls due to network/DNS issues.

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project content into the container
COPY . /app/

# Ensure logs directory exists
RUN mkdir -p /app/logs

# Expose the API port
EXPOSE 6000

# Default command: Runs the production server
CMD ["gunicorn", "--bind", "0.0.0.0:6000", "--timeout", "120", "app:create_app()"]
