FROM python:3.11-slim

WORKDIR /app

# System deps for biopython C extensions and gcc for some ML packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install tool dependencies first (larger, changes less often)
COPY tools/requirements.txt /app/tools/requirements.txt
RUN pip install --no-cache-dir -r /app/tools/requirements.txt

# Install backend dependencies
COPY backend/pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    "celery[redis]" \
    redis \
    "python-jose[cryptography]" \
    "passlib[bcrypt]" \
    python-multipart \
    "pydantic>=2.7.0" \
    "pydantic-settings>=2.2.1" \
    slowapi \
    httpx \
    python-dotenv \
    google-auth \
    google-auth-oauthlib \
    google-auth-httplib2 \
    google-api-python-client

# Copy application code
COPY backend/app /app/app

# Tools and workflows are mounted as volumes at runtime
# COPY tools /app/tools  ← NOT baked in; mounted read-only

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
