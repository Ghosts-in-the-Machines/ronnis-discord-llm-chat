FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_ROOT=/app/data \
    LOREBOOK_ROOT=none \
    CHARACTER_CARD=none

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY .env.example README.md LICENSE ./
COPY docker-entrypoint.sh /usr/local/bin/discord-llm-chat

RUN chmod +x /usr/local/bin/discord-llm-chat \
    && mkdir -p /app/data /app/lorebooks /app/character_cards /app/memory

VOLUME ["/app/data", "/app/lorebooks", "/app/character_cards", "/app/memory"]

ENTRYPOINT ["discord-llm-chat"]
