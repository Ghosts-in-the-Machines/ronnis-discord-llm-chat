# Ronni's Discord LLM Chat

Talk to an OpenAI-compatible LLM endpoint through Discord channels.

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

## How It Works

The Discord handler listens for messages and appends them to local JSONL logs in `DATA_ROOT`.

The worker polls for wake signals, checks each channel for messages newer than the last processed Discord message ID, builds a prompt, calls your LLM API, and queues replies back to Discord.

Generation settings such as `MAX_TOKENS`, `SEED`, `TOP_P`, `TOP_K`, penalties, character cards, lorebooks, and memory hooks are configured in `.env`.

Made by Ronni & Val.
