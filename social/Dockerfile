# social — Python 3.12 + Playwright (Chromium)
FROM python:3.12-slim

# Playwright Chromium system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpango-1.0-0 libcairo2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download embedding model at build time so first run is fast
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Install Playwright Chromium
RUN playwright install chromium
RUN playwright install-deps chromium || true

# Copy source (secrets and data are excluded via .dockerignore)
COPY . .

ENV PYTHONPATH=/app

# data/ and config.yaml are mounted at runtime, not baked in
# docker run --env-file .env -v $(pwd)/data:/app/data -v $(pwd)/config.yaml:/app/config.yaml ...
ENTRYPOINT ["python", "run_cli.py"]
