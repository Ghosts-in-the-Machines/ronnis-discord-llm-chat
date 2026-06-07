import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import (
    ACK_KEYWORD,
    ACK_MODE,
    CHAT_ARCHIVE_MAX_LINES,
    CHAT_ARCHIVE_ROOT,
    CTX_LIMIT,
    DATA_ROOT,
    HUMAN,
    CHARACTER_CARD,
    LOREBOOK_ROOT,
    MAX_STEPS,
    MODEL_CAPABILITY,
    MODEL_TIER,
    NAME,
    PULSE_BUDGET,
    PULSE_INTERVAL,
)
from llm_client import call_llm

try:
    from src.discord.character_card import CharacterCard
    from src.discord.decision import normalize_response_decision, resolve_ack_mode, response_format_for_ack_mode
    from src.discord.lore_parser import Lorebook
    from src.discord.memory import memory_prompt_block
    from src.discord.prompting import build_discord_prompt
    from src.discord.utils import append_chat_jsonl_locked, atomic_write_json, locked_file, push_json_queue, read_jsonl
except ImportError:
    from discord.character_card import CharacterCard
    from discord.decision import normalize_response_decision, resolve_ack_mode, response_format_for_ack_mode
    from discord.lore_parser import Lorebook
    from discord.memory import memory_prompt_block
    from discord.prompting import build_discord_prompt
    from discord.utils import append_chat_jsonl_locked, atomic_write_json, locked_file, push_json_queue, read_jsonl


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

STATE_FILE = os.path.join(DATA_ROOT, ".worker_state.json")
STATE_LOCK_FILE = os.path.join(DATA_ROOT, ".worker_state.lock")
WAKE_PATH = os.path.join(DATA_ROOT, ".discord_wake")
QUEUE_PATH = os.path.join(DATA_ROOT, ".discord_replies.json")
RESOLVED_ACK_MODE = resolve_ack_mode(MODEL_TIER, MODEL_CAPABILITY, ACK_MODE)
ACK_RESPONSE_FORMAT = response_format_for_ack_mode(RESOLVED_ACK_MODE)

_running = True


def _default_state() -> dict[str, Any]:
    return {
        "active_pulse": False,
        "last_message_id": {},
        "pulse_budget": PULSE_BUDGET,
        "last_wake_timestamp": 0.0,
        "last_pulse_at": None,
    }


def _load_state_unlocked() -> dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return _default_state()
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return _default_state()
    merged = _default_state()
    if isinstance(state, dict):
        merged.update(state)
    if not isinstance(merged.get("last_message_id"), dict):
        merged["last_message_id"] = {}
    return merged


def _save_state_unlocked(state: dict[str, Any]) -> None:
    atomic_write_json(STATE_FILE, state)


def _read_wake_timestamp() -> float:
    if not os.path.exists(WAKE_PATH):
        return 0.0
    try:
        with open(WAKE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return float(data.get("timestamp", 0.0))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        try:
            return os.path.getmtime(WAKE_PATH)
        except OSError:
            return 0.0


def _chat_files() -> list[Path]:
    root = Path(DATA_ROOT)
    return sorted(path for path in root.glob("discord_*.jsonl") if path.is_file())


def _message_id_value(message: dict[str, Any]) -> int:
    try:
        return int(message.get("_message_id") or 0)
    except (TypeError, ValueError):
        return 0


def _recent_messages(messages: list[dict[str, Any]], limit: int = 24) -> list[dict[str, Any]]:
    return messages[-limit:]


def _build_prompt(
    chat_id: str,
    messages: list[dict[str, Any]],
    lorebook: Lorebook | None,
    character_card: CharacterCard | None,
) -> list[dict[str, str]]:
    recent_messages = _recent_messages(messages)
    transcript = "\n".join(str(msg.get("content", "")) for msg in recent_messages)
    character = character_card.prompt_block() if character_card else ""
    lore = lorebook.query(transcript) if lorebook else ""
    memories = memory_prompt_block(transcript)
    return build_discord_prompt(
        chat_id,
        recent_messages,
        human=HUMAN,
        ctx_limit=CTX_LIMIT,
        character=character,
        lore=lore,
        memories=memories,
        ack_mode=RESOLVED_ACK_MODE,
        ack_keyword=ACK_KEYWORD,
    )


def _call_llm(messages: list[dict[str, str]]) -> str:
    return call_llm(messages, response_format=ACK_RESPONSE_FORMAT)


def _queue_reply(chat_id: str, content: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    push_json_queue(QUEUE_PATH, {"chat_id": chat_id, "content": content, "queued_at": now})
    append_chat_jsonl_locked(
        os.path.join(DATA_ROOT, f"{chat_id}.jsonl"),
        {
            "role": "assistant",
            "content": content,
            "timestamp": now,
            "status": "completed",
            "_platform": "discord",
            "_delivery": "queued",
        },
        CHAT_ARCHIVE_ROOT,
        CHAT_ARCHIVE_MAX_LINES,
    )


def pulse() -> None:
    with locked_file(STATE_LOCK_FILE, "a+", exclusive=True):
        state = _load_state_unlocked()
        if state.get("active_pulse"):
            return
        wake_timestamp = _read_wake_timestamp()
        if wake_timestamp <= float(state.get("last_wake_timestamp") or 0):
            return
        state["active_pulse"] = True
        state["last_wake_timestamp"] = wake_timestamp
        state["last_pulse_at"] = datetime.now(timezone.utc).isoformat()
        _save_state_unlocked(state)

    try:
        lorebook = Lorebook(LOREBOOK_ROOT) if LOREBOOK_ROOT else None
        character_card = CharacterCard(CHARACTER_CARD) if CHARACTER_CARD else None
        processed = 0
        for path in _chat_files():
            if processed >= MAX_STEPS:
                break
            chat_id = path.stem
            messages = read_jsonl(str(path))
            if not messages:
                continue
            last_seen = int(state.get("last_message_id", {}).get(chat_id, 0) or 0)
            newest = max((_message_id_value(item) for item in messages), default=0)
            new_user_messages = [
                item for item in messages
                if item.get("role") == "user" and _message_id_value(item) > last_seen
            ]
            if not new_user_messages:
                state["last_message_id"][chat_id] = max(last_seen, newest)
                continue

            raw_content = _call_llm(_build_prompt(chat_id, messages, lorebook, character_card))
            decision = normalize_response_decision(raw_content, ACK_KEYWORD)
            if decision["action"] == "reply" and decision["content"]:
                _queue_reply(chat_id, decision["content"])
                processed += 1
            state["last_message_id"][chat_id] = max(last_seen, newest)
    finally:
        with locked_file(STATE_LOCK_FILE, "a+", exclusive=True):
            current = _load_state_unlocked()
            current["active_pulse"] = False
            current["last_message_id"].update(state.get("last_message_id", {}))
            remaining = int(current.get("pulse_budget") or PULSE_BUDGET)
            current["pulse_budget"] = max(0, remaining - 1)
            _save_state_unlocked(current)


def _stop(signum, frame):
    global _running
    _running = False


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)

if __name__ == "__main__":
    interval = PULSE_INTERVAL
    logging.info(f"Discord worker starting. Poll interval: {interval}s")
    
    while _running:
        try:
            pulse()
        except Exception as e:
            logging.exception(f"Discord cycle failed: {e}")
        
        # Sleep in small increments to respect SIGTERM quickly
        for _ in range(interval * 10):
            if not _running: break
            time.sleep(0.1)
            
    logging.info("Worker shutting down gracefully.")
    sys.exit(0)
