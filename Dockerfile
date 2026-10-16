FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Version/Build-Datum (setzt die GitHub Action beim Bauen)
ARG APP_VERSION=dev
ARG APP_COMMIT=lokal
ARG BUILD_DATE=
ENV APP_VERSION=${APP_VERSION} APP_COMMIT=${APP_COMMIT} BUILD_DATE=${BUILD_DATE}

RUN useradd -r -u 1000 rcon && mkdir -p /data && chown rcon /data
USER rcon
VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/api/me')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
