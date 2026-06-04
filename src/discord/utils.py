import contextlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterator


if os.name == "nt":
    import msvcrt
else:
    import fcntl


@contextlib.contextmanager
def locked_file(path: str, mode: str = "a+", exclusive: bool = True) -> Iterator[Any]:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, mode, encoding="utf-8") as handle:
        if os.name == "nt":
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK if exclusive else msvcrt.LK_RLCK, 1)
            try:
                yield handle
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            try:
                yield handle
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_write_json(path: str, data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def load_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return default


def append_jsonl_locked(path: str, entry: dict[str, Any]) -> None:
    with locked_file(path, "a+", exclusive=True) as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_jsonl(path: str) -> list[dict[str, Any]]:
    if not os.path.exists(path):
        return []
    rows = []
    with locked_file(path, "r", exclusive=False) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def pop_json_queue(path: str) -> list[dict[str, Any]]:
    with locked_file(path, "a+", exclusive=True) as handle:
        handle.seek(0)
        try:
            queue = json.load(handle)
        except json.JSONDecodeError:
            queue = []
        if not isinstance(queue, list):
            queue = []
        handle.seek(0)
        handle.truncate()
        json.dump([], handle)
        handle.flush()
        os.fsync(handle.fileno())
        return [item for item in queue if isinstance(item, dict)]


def push_json_queue(path: str, entry: dict[str, Any]) -> None:
    with locked_file(path, "a+", exclusive=True) as handle:
        handle.seek(0)
        try:
            queue = json.load(handle)
        except json.JSONDecodeError:
            queue = []
        if not isinstance(queue, list):
            queue = []
        queue.append(entry)
        handle.seek(0)
        handle.truncate()
        json.dump(queue, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def sanitize_injection(text: str) -> str:
    safe = str(text or "").replace("<", "[[").replace(">", "]]")
    patterns = [
        r"ignore\s+all\s+previous\s+instructions",
        r"disregard\s+previous\s+directives?",
        r"system\s+override",
        r"you\s+are\s+now\s+a",
        r"new\s+rule\s*:",
        r"stop\s+following\s+your\s+core\s+rules",
        r"rootsystemprompt",
        r"important\s+new\s+instructions",
    ]
    for pattern in patterns:
        safe = re.sub(pattern, "[POSSIBLE_INJECTION_REMOVED]", safe, flags=re.IGNORECASE)
    return safe


def _sanitize_discord_text(text: str) -> str:
    safe_text = sanitize_injection(text)
    return (
        "--- UNTRUSTED DISCORD CONTENT START ---\n"
        f"{safe_text}\n"
        "--- UNTRUSTED DISCORD CONTENT END ---"
    )
