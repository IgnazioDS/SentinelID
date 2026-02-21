FROM python:3.11-slim

WORKDIR /app

RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --retries 5 --default-timeout=60 \
    fastapi==0.104.1 \
    uvicorn==0.24.0 \
    sqlalchemy==2.0.23 \
    psycopg2-binary==2.9.9 \
    cryptography==41.0.7 \
    httpx==0.25.1 \
    pydantic==2.5.0

COPY . .

CMD ["python", "-m", "main"]
