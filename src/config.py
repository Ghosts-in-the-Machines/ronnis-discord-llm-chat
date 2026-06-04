import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "y", "on"}


def _get_csv_ints(name: str) -> list[int]:
    values = []
    for raw in os.getenv(name, "").replace(";", ",").split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            values.append(int(raw))
        except ValueError:
            continue
    return values


DATA_ROOT = os.getenv("DATA_ROOT", "./data")
Path(DATA_ROOT).mkdir(parents=True, exist_ok=True)

PULSE_INTERVAL = _get_int("PULSE_INTERVAL", 180)
MAX_STEPS = _get_int("MAX_STEPS", 5)
PULSE_BUDGET = _get_int("PULSE_BUDGET", MAX_STEPS)
CTX_LIMIT = _get_int("CTX_LIMIT", 10000)
CHAT_TEMP = _get_float("CHAT_TEMP", 0.7)

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_PRIMARY_USER_ID = os.getenv("DISCORD_PRIMARY_USER_ID", "").strip()
DISCORD_GUILD_IDS = _get_csv_ints("DISCORD_GUILD_IDS")
HUMAN = os.getenv("HUMAN", "the primary user")
NAME = os.getenv("NAME", "discord-llm-worker")

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.getenv("API_KEY", os.getenv("OPENAI_API_KEY", "")).strip()
MODEL = os.getenv("MODEL", "gpt-4o-mini") 

LOREBOOK_ROOT = os.getenv("LOREBOOK_ROOT", "lorebooks")
REPLY_TO_BOTS = _get_bool("REPLY_TO_BOTS", False) # MAKE SURE THIS IS TRUE IF YOU WANT YOUR AI TO TALK TO OTHER AI!! default false for security


def get_discord_guild_ids() -> list[int]:
    return list(DISCORD_GUILD_IDS)
