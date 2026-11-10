FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false \
    DBT_VERSION_CHECK=false

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install . \
    && useradd --system --no-create-home --uid 10001 dbtwh \
    && install -d -o dbtwh /data

# Raw files, the warehouse and dbt's own files are all under /data (a volume or a bind mount). Nothing needs the network
# or a privilege: run with --network none, --read-only, --cap-drop ALL and --tmpfs /tmp (matplotlib's cache).
USER dbtwh
WORKDIR /data
VOLUME ["/data"]
ENTRYPOINT ["dbtwh"]
CMD ["--help"]
