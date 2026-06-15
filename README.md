# Ronni's Discord LLM Chat

Talk to an OpenAI-compatible or Anthropic Claude LLM endpoint through Discord channels.

This is a standalone Discord bridge with optional SillyTavern-style character cards, lorebooks, and memory hooks. It is designed for channel/server chat, not DMs.

## Setup

1. Copy `.env.example` to `.env`.
2. Fill in `DISCORD_BOT_TOKEN`, `API_BASE_URL`, `API_KEY`, and `MODEL`.
3. Optionally set `CHARACTER_CARD`, `LOREBOOK_ROOT`, and memory settings.
4. Run the startup script for your OS:

```bash
./run.sh
```

```bat
run.bat
```

The scripts create a virtual environment, install dependencies, and start both the Discord handler and worker.

## Docker

Build and run with Compose:

```bash
docker compose up -d --build
```

Compose reads `.env` through `env_file` and mounts runtime data into the container:

```text
./data -> /app/data
./chat_archive -> /app/chat_archive
./character_cards -> /app/character_cards
./lorebooks -> /app/lorebooks
./memory -> /app/memory
```

For Docker, set mounted paths in `.env`, for example `CHARACTER_CARD=/app/character_cards/card.png`, `LOREBOOK_ROOT=/app/lorebooks`, or `MEMORY_PROVIDER=local:/app/memory/memories.json`. Chat archives default to `/app/data/archive`; set `CHAT_ARCHIVE_ROOT=/app/chat_archive` to use the optional archive volume.

## How It Works

The Discord handler listens for messages and appends them to local JSONL logs in `DATA_ROOT`.

The worker polls for wake signals, checks each channel for messages newer than the last processed Discord message ID, builds a prompt, calls your LLM API, and queues replies back to Discord.

Generation settings such as `MAX_TOKENS`, `SEED`, `TOP_P`, `TOP_K`, penalties, `REASONING`, character cards, lorebooks, and memory hooks are configured in `.env`. Leave `REASONING` blank/off/none/omit to omit it, or set `REASONING=false` to send an explicit off value for compatible providers. `ACK_MODE=auto` uses JSON decisions for high/advanced models and an `[ACK]` keyword for standard, low, or quantized models; the worker normalizes either form before deciding whether to send a Discord reply. Set `PROMPT_MODE=direct` for local or quantized roleplay models that leak planning, analysis, or thinking text; direct mode skips the reply-decision wrapper and asks only for the Discord reply text. `CTX_LIMIT` caps the recent Discord transcript characters in the prompt; character cards, lore, and retrieved memories are preserved ahead of that slice.

`API_PROVIDER` can be `openai`, `anthropic`, `openrouter`, or `auto`. `auto` detects `openrouter.ai` as OpenRouter and `api.anthropic.com` as native Anthropic. OpenRouter uses the OpenAI-compatible payload with `HTTP-Referer` and `X-Title` headers from `.env`.

For native Claude, set `API_PROVIDER=anthropic`, `API_BASE_URL=https://api.anthropic.com`, `API_KEY` to your Anthropic key, and `MODEL` to a Claude model name. OpenAI-compatible Claude proxies should stay on `API_PROVIDER=openai`.

Made by Ronni & Val.
