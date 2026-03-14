FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies first for better layer caching.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --retries 10 --default-timeout 180 -r /app/requirements.txt

# Copy the full project.
COPY . /app

# Ensure runtime folders exist for sqlite and token artifacts.
RUN mkdir -p /app/data /app/tokens

EXPOSE 8000

CMD ["python", "run.py"]
