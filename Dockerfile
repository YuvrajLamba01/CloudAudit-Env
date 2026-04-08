FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ENABLE_WEB_INTERFACE=true

WORKDIR /app

COPY pyproject.toml README.md openenv.yaml uv.lock ./
COPY env ./env
COPY server ./server
COPY ui ./ui
COPY inference.py ./inference.py

RUN pip install --upgrade pip && pip install .

EXPOSE 7860

CMD ["python", "-m", "server.app"]
