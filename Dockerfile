# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Install dos2unix to fix potential Windows line-ending issues in scripts
RUN apt-get update && apt-get install -y dos2unix && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY ./requirements.txt /app/requirements.txt

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir --retries 10 --default-timeout 180 -r /app/requirements.txt

# Copy the wait-for-postgres script
COPY ./wait-for-postgres.sh /app/wait-for-postgres.sh
# Convert to Unix line endings and make executable
RUN dos2unix /app/wait-for-postgres.sh && chmod +x /app/wait-for-postgres.sh

# Copy the rest of the application's code into the container at /app
COPY . /app

# Create a directory for tokens
RUN mkdir -p /app/tokens

# Use Render-provided PORT in production; keep 8000 as local fallback.
CMD ["sh", "-c", "/app/wait-for-postgres.sh uvicorn web_app:app --host 0.0.0.0 --port ${PORT:-8000}"]
