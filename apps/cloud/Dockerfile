FROM python:3.11-slim

WORKDIR /app

COPY requirements-dev.txt ./

RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --retries 5 --default-timeout=60 -r requirements-dev.txt

COPY . .

CMD ["./scripts/start_cloud.sh"]
