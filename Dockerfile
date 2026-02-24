FROM python:3.14-slim

LABEL org.opencontainers.image.title="tracekit"
LABEL org.opencontainers.image.description="Tracekit web dashboard and tools"
LABEL org.opencontainers.image.license="CC-BY-NC-4.0"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/home/tracekit/.local/bin:${PATH}"

WORKDIR /app

# Install minimal system deps (libpq-dev needed for psycopg2 when not using binary)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . /app

# Install the package and its dependencies from pyproject.toml.
# [production] adds psycopg2-binary for PostgreSQL support.
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir ".[production]"

# Create a non-root user
RUN useradd --create-home --shell /bin/bash tracekit \
    && chown -R tracekit:tracekit /app

USER tracekit

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD curl -f http://127.0.0.1:5000/health || exit 1

ARG GIT_SHA
ENV SENTRY_RELEASE=${GIT_SHA}

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "--chdir", "/app/app", "main:app"]
