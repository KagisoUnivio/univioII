FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

USER app

EXPOSE 8000

CMD ["python", "-m", "univio", "--host", "0.0.0.0", "--port", "8000"]
