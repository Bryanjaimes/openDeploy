# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies (needed for some python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements files into the container
ARG BUILD_MODE=full
COPY backend/requirements.txt ./requirements.txt
COPY backend/requirements-lite.txt ./requirements-lite.txt

# Install packages based on build mode
RUN if [ "$BUILD_MODE" = "lite" ]; then \
        pip install --no-cache-dir -r requirements-lite.txt; \
    else \
        pip install --no-cache-dir -r requirements.txt; \
    fi

# Copy the current directory contents into the container at /app
COPY . .

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Define environment variable
ENV MODULE_NAME="backend.main"
ENV VARIABLE_NAME="app"
ENV PORT="8000"

# Run app.py when the container launches
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
