# Build stage
FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install .

# Runtime stage
FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /install /usr/local
COPY src/ src/

# Healthcheck
COPY src/healthcheck.py /app/healthcheck.py
RUN chmod +x /app/healthcheck.py
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python /app/healthcheck.py

ENTRYPOINT ["ovirt-mcp"]
