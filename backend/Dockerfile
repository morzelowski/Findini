FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --require-hashes -r requirements.txt

RUN useradd --uid 10001 --create-home findini \
 && mkdir -p /data/photos \
 && chown -R findini:findini /data
COPY --chown=findini:findini alembic.ini ./
COPY --chown=findini:findini alembic ./alembic
COPY --chown=findini:findini app ./app
COPY --chown=findini:findini scripts ./scripts
COPY --chown=findini:findini docker-entrypoint.sh ./
USER findini

EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=4).status==200 else 1)"
ENTRYPOINT ["./docker-entrypoint.sh"]
