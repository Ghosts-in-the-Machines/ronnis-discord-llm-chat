import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from config import CHAT_ARCHIVE_MAX_LINES, CHAT_ARCHIVE_ROOT, DATA_ROOT

try:
    from .utils import append_chat_jsonl_locked, push_json_queue
except ImportError:
    from utils import append_chat_jsonl_locked, push_json_queue


QUEUE_PATH = os.path.join(DATA_ROOT, ".discord_replies.json")


def queue_reply(chat_id: str, content: str) -> dict:
    """Thread-safe queue writer for outgoing Discord messages."""
    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "chat_id": chat_id,
        "content": str(content or ""),
        "queued_at": now,
    }
    push_json_queue(QUEUE_PATH, entry)
    append_chat_jsonl_locked(
        os.path.join(DATA_ROOT, f"{chat_id}.jsonl"),
        {
            "role": "assistant",
            "content": entry["content"],
            "timestamp": now,
            "status": "completed",
            "_platform": "discord",
            "_delivery": "queued",
        },
        CHAT_ARCHIVE_ROOT,
        CHAT_ARCHIVE_MAX_LINES,
    )
    return {"success": True, "queued": True, "target": chat_id}
