import os
import sys
from pathlib import Path
from typing import Any

SRC_ROOT = Path(__file__).resolve().parents[1]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from config import (
    ACK_KEYWORD,
    ACK_MODE,
    CHARACTER_CARD,
    CHAT_TEMP,
    CTX_LIMIT,
    DATA_ROOT,
    HUMAN,
    LOREBOOK_ROOT,
    MAX_TOKENS,
    MODEL_CAPABILITY,
    MODEL_TIER,
)
from llm_client import call_llm

try:
    from .character_card import CharacterCard
    from .decision import normalize_response_decision, resolve_ack_mode, response_format_for_ack_mode
    from .lore_parser import Lorebook
    from .memory import memory_prompt_block
    from .prompting import build_discord_prompt
    from .reply import queue_reply
    from .utils import read_jsonl
except ImportError:
    from character_card import CharacterCard
    from decision import normalize_response_decision, resolve_ack_mode, response_format_for_ack_mode
    from lore_parser import Lorebook
    from memory import memory_prompt_block
    from prompting import build_discord_prompt
    from reply import queue_reply
    from utils import read_jsonl


DISCORD_REPLY_CHAR_LIMIT = 3500
RESOLVED_ACK_MODE = resolve_ack_mode(MODEL_TIER, MODEL_CAPABILITY, ACK_MODE)
ACK_RESPONSE_FORMAT = response_format_for_ack_mode(RESOLVED_ACK_MODE)


def _discord_chat_path(chat_id: str) -> str:
    return os.path.join(DATA_ROOT, f"{chat_id}.jsonl")


def _available_discord_chat_ids() -> list[str]:
    root = Path(DATA_ROOT)
    return sorted(path.stem for path in root.glob("discord_*.jsonl"))


def _trim_discord_reply(content: str) -> str:
    text = (content or "").strip()
    if len(text) <= DISCORD_REPLY_CHAR_LIMIT:
        return text
    return text[:DISCORD_REPLY_CHAR_LIMIT].rstrip() + "\n\n[truncated for Discord]"


def _build_discord_generation_messages(chat_id: str, messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    transcript = "\n".join(str(msg.get("content", "")) for msg in messages)
    character = CharacterCard(CHARACTER_CARD).prompt_block() if CHARACTER_CARD else ""
    lore = Lorebook(LOREBOOK_ROOT).query(transcript) if LOREBOOK_ROOT else ""
    memories = memory_prompt_block(transcript)
    return build_discord_prompt(
        chat_id,
        messages,
        human=HUMAN,
        ctx_limit=CTX_LIMIT,
        character=character,
        lore=lore,
        memories=memories,
        include_decision_instruction=True,
        include_author_id=True,
        ack_mode=RESOLVED_ACK_MODE,
        ack_keyword=ACK_KEYWORD,
    )


def _call_llm(
    messages: list[dict[str, str]],
    temperature: float = CHAT_TEMP,
    max_tokens: int = MAX_TOKENS,
) -> str:
    try:
        return call_llm(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=ACK_RESPONSE_FORMAT,
        )
    except RuntimeError as exc:
        return f"[error: {exc}]"


def discord_read(chat_id: str, limit: int = 5, token_budget: int | None = None) -> dict:
    """Pull recent messages from a specific Discord stream."""
    messages = read_jsonl(_discord_chat_path(chat_id))
    if not messages:
        return {
            "success": False,
            "error": "Stream empty or unreachable",
            "chat_id": chat_id,
            "expected_path": _discord_chat_path(chat_id),
            "available_chat_ids": _available_discord_chat_ids(),
            "messages": [],
        }
    selected = messages[-limit:] if limit else messages
    return {
        "success": True,
        "messages": selected,
        "context_tokens": sum(len(str(item.get("content", "")).split()) for item in selected),
    }


def discord_chat(
    chat_id: str,
    limit: int = 12,
    token_budget: int = 10000,
    temperature: float = CHAT_TEMP,
    max_tokens: int = MAX_TOKENS,
) -> dict:
    """Generate and queue a Discord reply from local chat history."""
    ctx = discord_read(chat_id=chat_id, limit=limit, token_budget=token_budget)
    if not ctx.get("success"):
        return {"success": False, "error": f"Discord read failed: {ctx.get('error')}"}

    decision = normalize_response_decision(
        _call_llm(
            _build_discord_generation_messages(chat_id, ctx.get("messages", [])),
            temperature=temperature,
            max_tokens=max_tokens,
        ),
        ACK_KEYWORD,
    )
    content = _trim_discord_reply(decision["content"])
    if decision["action"] == "ack" or not content:
        return {"success": True, "decision": "acknowledge", "target": chat_id}

    queued = queue_reply(chat_id, content)
    queued["decision"] = "reply"
    queued["content"] = content
    return queued


def discord_send(
    chat_id: str,
    acknowledge: bool = False,
    limit: int = 12,
    token_budget: int = 10000,
    temperature: float = CHAT_TEMP,
    max_tokens: int = MAX_TOKENS,
    acknowledge_only: bool | None = None,
    content: str | None = None,
    generate: bool | None = None,
    **_: Any,
) -> dict:
    """Acknowledge a Discord stream, generate a reply, or queue direct content."""
    if acknowledge_only is not None:
        acknowledge = acknowledge_only
    if content and content.strip():
        return queue_reply(chat_id, _trim_discord_reply(content))
    if acknowledge:
        return {"success": True, "decision": "acknowledge", "target": chat_id}
    return discord_chat(
        chat_id=chat_id,
        limit=limit,
        token_budget=token_budget,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def discord_reply(chat_id: str, content: str) -> dict:
    """Queue an outbound Discord message."""
    return queue_reply(chat_id, _trim_discord_reply(content))
