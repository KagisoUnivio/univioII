# syntax=docker/dockerfile:1
FROM python:3.11-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade zlib1g \
    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' zlib1g)" ge '1:1.3.dfsg+really1.3.1-1+deb13u1' \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app && useradd --system --gid app app

COPY requirements.txt ./
# Keep Python build tools and their vendored libraries out of the runtime.
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip uninstall -y setuptools \
    && python -m pip check \
    && python -m pip uninstall -y pip

COPY src ./src

ADD --chmod=0644 \
    --checksum=sha256:8d8dc42958c7b9351846609d552b4b38f3b19c92c9d4816b2f814fd148fe18be \
    https://truststore.pki.rds.amazonaws.com/eu-north-1/eu-north-1-bundle.pem \
    /app/certs/rds-ca.pem

USER app

EXPOSE 8000

CMD ["python", "-m", "univio", "--host", "0.0.0.0", "--port", "8000"]
