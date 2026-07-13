# Single image for the whole FinPulse stack (API, ingest, dashboard).
# The root requirements.txt already contains every dependency, so one image is
# reused by all three services with a different start command each.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first so the layer is cached across code changes.
# psycopg2-binary ships manylinux wheels, so no compiler/libpq is needed.
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000 8501

# Default command runs the API; docker-compose overrides it per service.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
