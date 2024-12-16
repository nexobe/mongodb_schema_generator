FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY requirements.txt .
COPY setup.py .
COPY README.md .
COPY LICENSE .
COPY mongodb_schema_generator/ mongodb_schema_generator/
COPY .env .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install -e .

# Create directory for schema output
RUN mkdir -p schemas

ENTRYPOINT ["mongodb-schema-generator"]
CMD ["--config", "/app/config.yaml"]
