FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-web.txt

# Copy source
COPY src/ src/
COPY web/ web/
COPY pyproject.toml ./

# Install package so CLI tools and imports work
RUN pip install --no-cache-dir -e .

# Create data directory
RUN mkdir -p /app/data/exports

VOLUME /app/data

EXPOSE 8000
