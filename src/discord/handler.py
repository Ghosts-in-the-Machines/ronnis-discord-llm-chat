import asyncio
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import discord

SRC_ROOT = Path(__file__).resolve().parents[1]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from config import (
    CTX_LIMIT,
    DATA_ROOT,
    DISCORD_BOT_TOKEN,
    DISCORD_PRIMARY_USER_ID,
    HUMAN,
    REPLY_TO_BOTS,
    get_discord_guild_ids,
)

try:
    from .utils import (
        _sanitize_discord_text,
        append_jsonl_locked,
        atomic_write_json,
        pop_json_queue,
        sanitize_injection,
    )
except ImportError:
    from utils import (
        _sanitize_discord_text,
        append_jsonl_locked,
        atomic_write_json,
        pop_json_queue,
        sanitize_injection,
    )

GUILD_IDS = get_discord_guild_ids()
QUEUE_PATH = os.path.join(DATA_ROOT, ".discord_replies.json")
WAKE_PATH = os.path.join(DATA_ROOT, ".discord_wake")
DISCORD_MESSAGE_LIMIT = min(3900, max(1000, int(CTX_LIMIT * 0.75)))
DISCORD_SAFE_CHUNK = 3900

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
intents.guild_messages = True

client = discord.Client(intents=intents)


def _chunk_discord_content(content: str) -> list[str]:
    text = str(content or "")
    if not text:
        return []

    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= DISCORD_MESSAGE_LIMIT:
            chunks.append(remaining)
            break

        split_at = remaining.rfind("\n", 0, DISCORD_SAFE_CHUNK)
        if split_at < 500:
            split_at = remaining.rfind(" ", 0, DISCORD_SAFE_CHUNK)
        if split_at < 500:
            split_at = DISCORD_SAFE_CHUNK

        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    return chunks

def _chat_path(chat_id: str) -> str:
    return os.path.join(DATA_ROOT, f"{chat_id}.jsonl")

@client.event
async def on_ready():
    guild_labels = []
    for guild_id in GUILD_IDS:
        guild = client.get_guild(guild_id)
        guild_labels.append(f"{guild.name} ({guild.id})" if guild else str(guild_id))
    print(f"[DISCORD] Anchored to {', '.join(guild_labels) or 'all visible guilds'}")
    print(f"[DISCORD] DATA_ROOT={DATA_ROOT}")
    print(f"[DISCORD] CHAT_DIR={DATA_ROOT}")
    print(
        "[DISCORD] Intents: "
        f"guilds={intents.guilds} messages={intents.messages} "
        f"guild_messages={intents.guild_messages} message_content={intents.message_content}"
    )
    # Start non-blocking queue processor
    asyncio.create_task(_flush_replies())


async def _flush_replies():
    while True:
        if os.path.exists(QUEUE_PATH):
            try:
                queue = pop_json_queue(QUEUE_PATH)
                for item in queue:
                    _, _, channel_id = item.get("chat_id", "").rpartition("_")
                    if not channel_id:
                        continue
                    channel = client.get_channel(int(channel_id))
                    if not channel:
                        continue
                    chunks = _chunk_discord_content(item.get("content", ""))
                    for idx, chunk in enumerate(chunks):
                        suffix = f"\n\n[{idx + 1}/{len(chunks)}]" if len(chunks) > 1 else ""
                        await channel.send(chunk[: DISCORD_MESSAGE_LIMIT - len(suffix)] + suffix)
            except Exception as e:
                print(f"[DISCORD] Flush error: {e}")
        await asyncio.sleep(2)


@client.event
async def on_message(message):
    guild_id = message.guild.id if message.guild else None
    print(
        "[DISCORD] on_message "
        f"guild={guild_id} channel={getattr(message.channel, 'id', None)} "
        f"author={getattr(message.author, 'id', None)} bot={getattr(message.author, 'bot', None)} "
        f"content_len={len(message.content or '')}"
    )

    if client.user and message.author.id == client.user.id:
        print("[DISCORD] Ignored message: author is this Discord bot")
        return
    if message.author.bot and not REPLY_TO_BOTS:
        print("[DISCORD] Ignored message: author is a bot")
        return
    if not message.guild:
        print("[DISCORD] Ignored message: no guild")
        return
    if GUILD_IDS and message.guild.id not in GUILD_IDS:
        print(f"[DISCORD] Ignored message: guild {message.guild.id} not in configured guild IDs")
        return

    chat_id = f"discord_{message.guild.id}_{message.channel.id}"
    author_id = str(message.author.id)
    is_primary_user = bool(DISCORD_PRIMARY_USER_ID and author_id == DISCORD_PRIMARY_USER_ID)

    msg_entry = {
        "role": "user",
        "content": _sanitize_discord_text(message.content),
        "status": "pending",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "_platform": "discord",
        "_message_id": str(message.id),
        "_author_id": author_id,
        "_author_name": sanitize_injection(message.author.display_name),
        "_author_is_bot": bool(message.author.bot),
        "_channel_id": str(message.channel.id),
        "_is_primary_user": is_primary_user,
    }
    if is_primary_user:
        msg_entry["_primary_user_name"] = HUMAN

    try:
        append_jsonl_locked(_chat_path(chat_id), msg_entry)
        print(
            f"[DISCORD] Ingested chat_id={chat_id} author={msg_entry['_author_name']} "
            f"message_id={msg_entry['_message_id']} path={_chat_path(chat_id)}"
        )
        atomic_write_json(WAKE_PATH, {"timestamp": time.time(), "chat_id": chat_id})
        print("[DISCORD] Wake signal set.")
    except Exception as exc:
        print(f"[DISCORD] Write failed: {exc}")


@client.event
async def on_error(event, *args, **kwargs):
    print(f"[DISCORD] Event error in {event}")
    traceback.print_exc()

if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN is required")
    client.run(DISCORD_BOT_TOKEN)
