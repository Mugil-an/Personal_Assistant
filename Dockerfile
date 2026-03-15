# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY ./requirements.txt /app/requirements.txt

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir --retries 10 --default-timeout 180 -r /app/requirements.txt

# Copy the wait-for-postgres script
COPY ./wait-for-postgres.sh /app/wait-for-postgres.sh
RUN chmod +x /app/wait-for-postgres.sh

# Copy the rest of the application's code into the container at /app
COPY . /app

# Create a directory for tokens
RUN mkdir -p /app/tokens

# The command to run the application will be specified in docker-compose.yml
# This makes the Dockerfile more reusable for different environments.
# Example command is provided in docker-compose.yml
CMD ["/app/wait-for-postgres.sh", "uvicorn", "web_app:app", "--host", "0.0.0.0", "--port", "8000"]

