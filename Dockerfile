FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies first for better layer caching.
COPY requirements.txt /app/requirements.txt
RUN apt-get update && apt-get install -y postgresql-client && \
    pip install --no-cache-dir --retries 10 --default-timeout 180 -r /app/requirements.txt

# Copy the wait script and the full project.
COPY ./wait-for-postgres.sh /app/wait-for-postgres.sh
RUN chmod +x /app/wait-for-postgres.sh
COPY . /app

# Ensure runtime folders exist for token artifacts.
RUN mkdir -p /app/tokens

EXPOSE 8000

CMD ["/app/wait-for-postgres.sh", "db", "python", "run.py"]
