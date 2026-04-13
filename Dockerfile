FROM python:3.11-slim

LABEL maintainer="NAE Platform"
LABEL description="NAE Platform — AI-Assisted Trading Research Infrastructure"

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application
COPY nae/ ./nae/
COPY config.example.yaml .
COPY examples/ ./examples/
COPY legal/ ./legal/
COPY pyproject.toml .

# Install NAE as package
RUN pip install --no-cache-dir .

# Create workspace dirs
RUN mkdir -p /app/logs /app/data /app/reports /app/strategies

# Non-root user for security
RUN useradd -m -s /bin/bash naeuser && chown -R naeuser:naeuser /app
USER naeuser

ENTRYPOINT ["nae"]
CMD ["status"]
