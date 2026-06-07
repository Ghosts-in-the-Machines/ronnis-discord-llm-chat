import json
import re
from typing import Any


DISABLED_VALUES = {"", "none", "null", "false", "0", "off"}


def _clean_mode(value: str) -> str:
    return str(value or "").strip().lower()


def resolve_ack_mode(model_tier: str, model_capability: str, ack_mode: str) -> str:
    requested = _clean_mode(ack_mode)
    if requested in {"json", "keyword"}:
        return requested
    if requested in DISABLED_VALUES:
        return "none"

    capability = _clean_mode(model_capability)
    tier = _clean_mode(model_tier)
    if capability == "standard":
        return "keyword"
    if capability == "advanced":
        return "json"
    if tier == "high":
        return "json"
    return "keyword"


def response_format_for_ack_mode(ack_mode: str) -> dict[str, Any] | None:
    if ack_mode != "json":
        return None
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "discord_response_decision",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "action": {"type": "string", "enum": ["reply", "ack"]},
                    "content": {"type": "string"},
                },
                "required": ["action", "content"],
            },
        },
    }


def _strip_code_fence(text: str) -> str:
    match = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", text, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else text.strip()


def _coerce_action(value: Any, content: str) -> str:
    action = str(value or "").strip().lower()
    if action in {"ack", "acknowledge", "none", "no_reply", "no-reply", "skip", "ignore"}:
        return "ack"
    if action in {"reply", "respond", "message"}:
        return "reply" if content else "ack"
    return "reply" if content else "ack"


def normalize_response_decision(raw: str, ack_keyword: str = "[ACK]") -> dict[str, str]:
    text = str(raw or "").strip()
    keyword = str(ack_keyword or "[ACK]").strip()
    if not text:
        return {"action": "ack", "content": ""}
    if keyword and text.casefold() == keyword.casefold():
        return {"action": "ack", "content": ""}

    candidate = _strip_code_fence(text)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return {"action": "reply", "content": text}

    if not isinstance(parsed, dict):
        return {"action": "reply", "content": text}

    content = str(parsed.get("content") or parsed.get("reply") or parsed.get("message") or "").strip()
    action = _coerce_action(parsed.get("action") or parsed.get("decision"), content)
    if action == "ack":
        return {"action": "ack", "content": ""}
    return {"action": "reply", "content": content or text}
