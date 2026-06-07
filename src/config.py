import os
import json
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


def _get_optional_int(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _get_optional_float(name: str) -> float | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


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


def _get_optional_json_or_string(name: str) -> object | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    if value.lower() in {"off", "none", "null", "omit"}:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


DATA_ROOT = os.getenv("DATA_ROOT", "./data")
Path(DATA_ROOT).mkdir(parents=True, exist_ok=True)
_raw_chat_archive_root = os.getenv("CHAT_ARCHIVE_ROOT", "").strip()
CHAT_ARCHIVE_ROOT = _raw_chat_archive_root or str(Path(DATA_ROOT) / "archive")
CHAT_ARCHIVE_MAX_LINES = _get_int("CHAT_ARCHIVE_MAX_LINES", 5000)
if CHAT_ARCHIVE_MAX_LINES > 0:
    Path(CHAT_ARCHIVE_ROOT).mkdir(parents=True, exist_ok=True)

PULSE_INTERVAL = _get_int("PULSE_INTERVAL", 180)
MAX_STEPS = _get_int("MAX_STEPS", 5)
PULSE_BUDGET = _get_int("PULSE_BUDGET", MAX_STEPS)
CTX_LIMIT = _get_int("CTX_LIMIT", 10000)
CHAT_TEMP = _get_float("CHAT_TEMP", 0.7)
MAX_TOKENS = _get_int("MAX_TOKENS", 1200)
SEED = _get_optional_int("SEED")
TOP_P = _get_optional_float("TOP_P")
TOP_K = _get_optional_int("TOP_K")
MIN_P = _get_optional_float("MIN_P")
FREQUENCY_PENALTY = _get_optional_float("FREQUENCY_PENALTY")
PRESENCE_PENALTY = _get_optional_float("PRESENCE_PENALTY")
REPETITION_PENALTY = _get_optional_float("REPETITION_PENALTY")
REASONING = _get_optional_json_or_string("REASONING")

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_PRIMARY_USER_ID = os.getenv("DISCORD_PRIMARY_USER_ID", "").strip()
DISCORD_GUILD_IDS = _get_csv_ints("DISCORD_GUILD_IDS")
MESSAGE_FIRST_TIMER = _get_optional_int("MESSAGE_FIRST_TIMER")
MESSAGE_FIRST_CHANNEL_IDS = _get_csv_ints("MESSAGE_FIRST_CHANNEL_IDS")
HUMAN = os.getenv("HUMAN", "the primary user")
NAME = os.getenv("NAME", "discord-llm-worker")

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.getenv("API_KEY", os.getenv("OPENAI_API_KEY", "")).strip()
MODEL = os.getenv("MODEL", "gpt-4o-mini")
MODEL_TIER = os.getenv("MODEL_TIER", "auto").strip().lower()
MODEL_CAPABILITY = os.getenv("MODEL_CAPABILITY", "auto").strip().lower()
ACK_MODE = os.getenv("ACK_MODE", "auto").strip().lower()
ACK_KEYWORD = os.getenv("ACK_KEYWORD", "[ACK]").strip() or "[ACK]"
_raw_api_provider = os.getenv("API_PROVIDER", "auto").strip().lower()
OPENROUTER_HTTP_REFERER = os.getenv("OPENROUTER_HTTP_REFERER", "https://discord-llm-chat.local").strip()
OPENROUTER_X_TITLE = os.getenv("OPENROUTER_X_TITLE", "Ronni's Discord LLM Chat").strip()


def _detect_api_provider(provider: str, base_url: str) -> str:
    if provider != "auto":
        return provider if provider in {"openai", "anthropic", "openrouter"} else "openai"
    base = base_url.lower()
    if "openrouter.ai" in base:
        return "openrouter"
    if "api.anthropic.com" in base:
        return "anthropic"
    return "openai"


API_PROVIDER = _detect_api_provider(_raw_api_provider, API_BASE_URL)

_raw_lorebook_root = os.getenv("LOREBOOK_ROOT", "none").strip()
LOREBOOK_ROOT = None if _raw_lorebook_root.lower() in {"", "none", "null", "false", "0", "off"} else _raw_lorebook_root
REPLY_TO_BOTS = _get_bool("REPLY_TO_BOTS", False) # MAKE SURE THIS IS TRUE IF YOU WANT YOUR AI TO TALK TO OTHER AI!! default false for security

_raw_character_card = os.getenv("CHARACTER_CARD", "none").strip()
CHARACTER_CARD = None if _raw_character_card.lower() in {"", "none", "null", "false", "0", "off"} else _raw_character_card

USE_MEM = _get_bool("USE_MEM", False)
MEMORY_PROVIDER = os.getenv("MEMORY_PROVIDER", "none").strip().lower()
MEMORY_TOP_K = _get_int("MEMORY_TOP_K", 5)
MEMORY_MIN_SCORE = _get_float("MEMORY_MIN_SCORE", 0.0)
MEMORY_API_URL = os.getenv("MEMORY_API_URL", "").strip()
MEMORY_API_KEY = os.getenv("MEMORY_API_KEY", "").strip()

QDRANT_URL = os.getenv("QDRANT_URL", "").rstrip("/")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "").strip()
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "").strip()
QDRANT_VECTOR_NAME = os.getenv("QDRANT_VECTOR_NAME", "").strip()
EMBEDDING_API_URL = os.getenv("EMBEDDING_API_URL", "").strip()
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", API_KEY).strip()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "").strip()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "memories").strip()
SUPABASE_TEXT_COLUMN = os.getenv("SUPABASE_TEXT_COLUMN", "content").strip()
SUPABASE_RPC = os.getenv("SUPABASE_RPC", "").strip()


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


def anthropic_messages_url() -> str:
    base = API_BASE_URL.rstrip("/")
    if base.endswith("/messages"):
        return base
    if base.endswith("/v1"):
        return f"{base}/messages"
    return f"{base}/v1/messages"


def generation_params(
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict:
    params = {
        "temperature": CHAT_TEMP if temperature is None else temperature,
        "max_tokens": MAX_TOKENS if max_tokens is None else max_tokens,
    }
    optional = {
        "seed": SEED,
        "top_p": TOP_P,
        "top_k": TOP_K,
        "min_p": MIN_P,
        "frequency_penalty": FREQUENCY_PENALTY,
        "presence_penalty": PRESENCE_PENALTY,
        "repetition_penalty": REPETITION_PENALTY,
        "reasoning": REASONING,
    }
    return {key: value for key, value in {**params, **optional}.items() if value is not None}
