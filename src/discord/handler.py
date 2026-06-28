import asyncio
import json
import os
import random
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
    ACK_MODE,
    CHAT_ARCHIVE_MAX_LINES,
    CHAT_ARCHIVE_ROOT,
    CTX_LIMIT,
    DATA_ROOT,
    DISCORD_BOT_TOKEN,
    DISCORD_PRIMARY_USER_ID,
    HUMAN,
    MESSAGE_FIRST_CHANNEL_IDS,
    MESSAGE_FIRST_TIMER,
    MODEL_CAPABILITY,
    MODEL_TIER,
    REPLY_TO_BOTS,
    get_discord_guild_ids,
)

try:
    from .decision import resolve_ack_mode
    from .utils import (
        _sanitize_discord_text,
        append_chat_jsonl_locked,
        atomic_write_json,
        pop_json_queue,
        read_jsonl,
        sanitize_injection,
    )
except ImportError:
    from decision import resolve_ack_mode
    from utils import (
        _sanitize_discord_text,
        append_chat_jsonl_locked,
        atomic_write_json,
        pop_json_queue,
        read_jsonl,
        sanitize_injection,
    )

GUILD_IDS = get_discord_guild_ids()
QUEUE_PATH = os.path.join(DATA_ROOT, ".discord_replies.json")
WAKE_PATH = os.path.join(DATA_ROOT, ".discord_wake")
DISCORD_MESSAGE_LIMIT = min(3900, max(1000, int(CTX_LIMIT * 0.75)))
DISCORD_SAFE_CHUNK = 3900
RESOLVED_ACK_MODE = resolve_ack_mode(MODEL_TIER, MODEL_CAPABILITY, ACK_MODE)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
intents.guild_messages = True

client = discord.Client(intents=intents)
message_first_task: asyncio.Task | None = None


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


def _guild_channel_metadata(guild: discord.Guild, channel: discord.abc.GuildChannel) -> dict[str, str]:
    return {
        "_guild_id": str(guild.id),
        "_guild_name": sanitize_injection(guild.name),
        "_channel_id": str(channel.id),
        "_channel_name": sanitize_injection(getattr(channel, "name", str(channel.id))),
    }


def _visible_message_first_channels() -> list[discord.TextChannel]:
    channels = []
    configured_ids = set(MESSAGE_FIRST_CHANNEL_IDS)
    for guild in client.guilds:
        if GUILD_IDS and guild.id not in GUILD_IDS:
            continue
        for channel in guild.text_channels:
            if configured_ids and channel.id not in configured_ids:
                continue
            permissions = channel.permissions_for(guild.me)
            if permissions.view_channel and permissions.send_messages:
                channels.append(channel)
    return channels


def _message_first_prompt() -> str:
    if RESOLVED_ACK_MODE == "json":
        return (
            "MESSAGE_FIRST_TIMER:\n"
            "This Discord channel has been silent for the configured interval. "
            "Decide whether to start a new conversation, continue the existing channel "
            "conversation if that feels acceptable, or pass. If you pass, return a silent "
            "acknowledgement according to your configured JSON response mode."
        )
    return (
        "MESSAGE_FIRST_TIMER:\n"
        "This Discord channel has been silent for the configured interval. Start a new "
        "conversation or continue the existing channel conversation if that feels natural."
    )


def _parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _last_channel_activity_at(chat_id: str) -> datetime | None:
    last_activity = None
    for item in read_jsonl(_chat_path(chat_id)):
        if item.get("_message_first_timer"):
            continue
        timestamp = _parse_timestamp(item.get("timestamp"))
        if timestamp and (last_activity is None or timestamp > last_activity):
            last_activity = timestamp
    return last_activity


def _channel_is_silent(chat_id: str) -> bool:
    last_activity = _last_channel_activity_at(chat_id)
    if last_activity is None:
        return True
    silent_for = datetime.now(timezone.utc) - last_activity
    return silent_for.total_seconds() >= MESSAGE_FIRST_TIMER * 60


def _next_message_first_id(chat_id: str) -> str:
    discord_epoch_ms = 1420070400000
    now_ms = int(time.time() * 1000)
    synthetic_snowflake = max(0, now_ms - discord_epoch_ms) << 22
    newest = 0
    for item in read_jsonl(_chat_path(chat_id)):
        try:
            newest = max(newest, int(item.get("_message_id") or 0))
        except (TypeError, ValueError):
            continue
    return str(max(synthetic_snowflake, newest + 1))


async def _message_first_loop() -> None:
    if not MESSAGE_FIRST_TIMER or MESSAGE_FIRST_TIMER <= 0:
        return
    interval_seconds = MESSAGE_FIRST_TIMER * 60
    while True:
        await asyncio.sleep(interval_seconds)
        channels = [
            channel for channel in _visible_message_first_channels()
            if _channel_is_silent(f"discord_{channel.guild.id}_{channel.id}")
        ]
        if not channels:
            print("[DISCORD] MESSAGE_FIRST_TIMER skipped: no eligible silent channels")
            continue
        channel = random.choice(channels)
        chat_id = f"discord_{channel.guild.id}_{channel.id}"
        now = datetime.now(timezone.utc).isoformat()
        msg_entry = {
            "role": "user",
            "content": _message_first_prompt(),
            "status": "pending",
            "timestamp": now,
            "_platform": "discord",
            "_message_id": _next_message_first_id(chat_id),
            "_author_id": "MESSAGE_FIRST_TIMER",
            "_author_name": "MESSAGE_FIRST_TIMER",
            "_author_is_bot": True,
            "_message_first_timer": True,
            **_guild_channel_metadata(channel.guild, channel),
        }
        try:
            append_chat_jsonl_locked(_chat_path(chat_id), msg_entry, CHAT_ARCHIVE_ROOT, CHAT_ARCHIVE_MAX_LINES)
            atomic_write_json(WAKE_PATH, {"timestamp": time.time(), "chat_id": chat_id})
            print(f"[DISCORD] MESSAGE_FIRST_TIMER prompted chat_id={chat_id} path={_chat_path(chat_id)}")
        except Exception as exc:
            print(f"[DISCORD] MESSAGE_FIRST_TIMER write failed: {exc}")

@client.event
async def on_ready():
    global message_first_task
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
    if MESSAGE_FIRST_TIMER and MESSAGE_FIRST_TIMER > 0 and (message_first_task is None or message_first_task.done()):
        message_first_task = asyncio.create_task(_message_first_loop())
        channel_label = (
            ", ".join(str(channel_id) for channel_id in MESSAGE_FIRST_CHANNEL_IDS)
            if MESSAGE_FIRST_CHANNEL_IDS
            else "random visible channel"
        )
        print(f"[DISCORD] MESSAGE_FIRST_TIMER enabled every {MESSAGE_FIRST_TIMER} minute(s): {channel_label}")


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
        "_is_primary_user": is_primary_user,
        **_guild_channel_metadata(message.guild, message.channel),
    }
    if is_primary_user:
        msg_entry["_primary_user_name"] = HUMAN

    try:
        append_chat_jsonl_locked(_chat_path(chat_id), msg_entry, CHAT_ARCHIVE_ROOT, CHAT_ARCHIVE_MAX_LINES)
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
