import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        env_path = Path(".env")
        if not env_path.exists():
            return False
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
        return False


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

_raw_lorebook_root = os.getenv("LOREBOOK_ROOT", "none").strip()
LOREBOOK_ROOT = None if _raw_lorebook_root.lower() in {"", "none", "null", "false", "0", "off"} else _raw_lorebook_root
REPLY_TO_BOTS = _get_bool("REPLY_TO_BOTS", False) # MAKE SURE THIS IS TRUE IF YOU WANT YOUR AI TO TALK TO OTHER AI!! default false for security


def get_discord_guild_ids() -> list[int]:
    return list(DISCORD_GUILD_IDS)


def chat_completions_url() -> str:
    base = API_BASE_URL.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if "api.deepseek.com" in base and base.endswith("/v1"):
        return f"{base[:-3]}/chat/completions"
    if "api.deepseek.com" in base:
        return f"{base}/chat/completions"
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"
