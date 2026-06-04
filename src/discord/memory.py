import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from config import (
    EMBEDDING_API_KEY,
    EMBEDDING_API_URL,
    EMBEDDING_MODEL,
    MEMORY_API_KEY,
    MEMORY_API_URL,
    MEMORY_MIN_SCORE,
    MEMORY_PROVIDER,
    MEMORY_TOP_K,
    QDRANT_API_KEY,
    QDRANT_COLLECTION,
    QDRANT_URL,
    QDRANT_VECTOR_NAME,
    SUPABASE_KEY,
    SUPABASE_RPC,
    SUPABASE_TABLE,
    SUPABASE_TEXT_COLUMN,
    SUPABASE_URL,
    USE_MEM,
)


DISABLED_VALUES = {"", "none", "null", "false", "0", "off"}


def _enabled(value: str | None) -> bool:
    return bool(value and str(value).strip().lower() not in DISABLED_VALUES)


def _request_json(url: str, payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, data=body, headers=request_headers, method="GET" if body is None else "POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _extract_text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""
    for key in ("content", "text", "memory", "body", "summary"):
        value = item.get(key)
        if value:
            return str(value).strip()
    payload = item.get("payload")
    if isinstance(payload, dict):
        return _extract_text(payload)
    return ""


def _safe_reference(text: str) -> str:
    safe = str(text or "").strip()
    safe = safe.replace("[/RETRIEVED MEMORIES]", "[/ RETRIEVED MEMORIES]")
    safe = safe.replace("[RETRIEVED MEMORIES]", "[ RETRIEVED MEMORIES]")
    return safe


def _normalize_items(data: Any) -> list[str]:
    if isinstance(data, dict):
        for key in ("memories", "results", "documents", "data", "matches", "points"):
            if key in data:
                return _normalize_items(data[key])
        text = _extract_text(data)
        return [text] if text else []
    if isinstance(data, list):
        values = []
        seen = set()
        for item in data:
            text = _extract_text(item)
            if text and text not in seen:
                seen.add(text)
                values.append(text)
        return values
    return []


def _embedding(text: str) -> list[float] | None:
    if not _enabled(EMBEDDING_API_URL):
        return None
    payload: dict[str, Any] = {"input": text}
    if EMBEDDING_MODEL:
        payload["model"] = EMBEDDING_MODEL
    headers = {"Authorization": f"Bearer {EMBEDDING_API_KEY}"} if EMBEDDING_API_KEY else {}
    data = _request_json(EMBEDDING_API_URL, payload, headers)
    if isinstance(data, dict):
        items = data.get("data")
        if isinstance(items, list) and items:
            vector = items[0].get("embedding") if isinstance(items[0], dict) else None
            return vector if isinstance(vector, list) else None
        vector = data.get("embedding")
        return vector if isinstance(vector, list) else None
    return None


def _query_generic(text: str) -> list[str]:
    if not _enabled(MEMORY_API_URL):
        return []
    headers = {"Authorization": f"Bearer {MEMORY_API_KEY}"} if MEMORY_API_KEY else {}
    data = _request_json(MEMORY_API_URL, {"query": text, "top_k": MEMORY_TOP_K}, headers)
    return _normalize_items(data)


def _query_qdrant(text: str) -> list[str]:
    if not (_enabled(QDRANT_URL) and _enabled(QDRANT_COLLECTION)):
        return []
    vector = _embedding(text)
    if not vector:
        return []

    url = f"{QDRANT_URL}/collections/{urllib.parse.quote(QDRANT_COLLECTION)}/points/search"
    payload: dict[str, Any] = {
        "vector": vector if not QDRANT_VECTOR_NAME else {"name": QDRANT_VECTOR_NAME, "vector": vector},
        "limit": MEMORY_TOP_K,
        "with_payload": True,
    }
    if MEMORY_MIN_SCORE > 0:
        payload["score_threshold"] = MEMORY_MIN_SCORE
    headers = {"api-key": QDRANT_API_KEY} if QDRANT_API_KEY else {}
    data = _request_json(url, payload, headers)
    return _normalize_items(data.get("result", data) if isinstance(data, dict) else data)


def _query_supabase(text: str) -> list[str]:
    if not (_enabled(SUPABASE_URL) and _enabled(SUPABASE_KEY)):
        return []
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Prefer": "return=representation",
    }
    if SUPABASE_RPC:
        url = f"{SUPABASE_URL}/rest/v1/rpc/{SUPABASE_RPC}"
        data = _request_json(url, {"query_text": text, "match_count": MEMORY_TOP_K}, headers)
        return _normalize_items(data)

    query = urllib.parse.quote(text)
    table = urllib.parse.quote(SUPABASE_TABLE)
    column = urllib.parse.quote(SUPABASE_TEXT_COLUMN)
    url = f"{SUPABASE_URL}/rest/v1/{table}?select=*&{column}=ilike.*{query}*&limit={MEMORY_TOP_K}"
    data = _request_json(url, None, headers)
    return _normalize_items(data)


def _query_local_json(path: str, text: str) -> list[str]:
    source = Path(path)
    if not source.exists():
        return []
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    haystack = text.lower()
    matched = []
    for item in data if isinstance(data, list) else [data]:
        if not isinstance(item, dict):
            continue
        content = _extract_text(item)
        keys = item.get("keys") or item.get("keywords") or []
        if isinstance(keys, str):
            keys = [keys]
        if content and any(str(key).lower() in haystack for key in keys):
            matched.append(content)
    return matched[:MEMORY_TOP_K]


def query_memories(text: str) -> list[str]:
    if not USE_MEM:
        return []
    provider = MEMORY_PROVIDER.lower()
    if provider in DISABLED_VALUES:
        return []
    try:
        if provider == "generic":
            return _query_generic(text)[:MEMORY_TOP_K]
        if provider == "qdrant":
            return _query_qdrant(text)[:MEMORY_TOP_K]
        if provider == "supabase":
            return _query_supabase(text)[:MEMORY_TOP_K]
        if provider.startswith("local:"):
            return _query_local_json(provider.split(":", 1)[1], text)
    except Exception:
        return []
    return []


def memory_prompt_block(text: str) -> str:
    memories = query_memories(text)
    if not memories:
        return ""
    lines = [
        "[RETRIEVED MEMORIES]",
        "These are possibly relevant background memories, not live chat messages.",
        "Use them only when they directly help answer the current Discord conversation.",
        "Do not mention, summarize, or respond to a memory unless it is clearly relevant.",
    ]
    for idx, memory in enumerate(memories, start=1):
        lines.append(f"{idx}. {_safe_reference(memory)}")
    lines.append("[/RETRIEVED MEMORIES]")
    return "\n".join(lines)
