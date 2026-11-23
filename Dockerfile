# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

ADD --chmod=0644 \
    --checksum=sha256:8d8dc42958c7b9351846609d552b4b38f3b19c92c9d4816b2f814fd148fe18be \
    https://truststore.pki.rds.amazonaws.com/eu-north-1/eu-north-1-bundle.pem \
    /app/certs/rds-ca.pem

USER app

EXPOSE 8000

CMD ["python", "-m", "univio", "--host", "0.0.0.0", "--port", "8000"]
