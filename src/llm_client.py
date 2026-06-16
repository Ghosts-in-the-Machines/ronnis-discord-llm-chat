import json
import re
import urllib.error
import urllib.request

from config import (
    API_KEY,
    API_PROVIDER,
    MODEL,
    OPENAI_EXTRA_BODY,
    OPENROUTER_HTTP_REFERER,
    OPENROUTER_X_TITLE,
    STRIP_THINKING_BLOCKS,
    anthropic_messages_url,
    chat_completions_url,
    generation_params,
)


_THINKING_BLOCK_PATTERNS = [
    re.compile(
        r"<\s*(think|thinking|reasoning|analysis)\s*>.*?<\s*/\s*\1\s*>",
        flags=re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\[\s*(think|thinking|reasoning|analysis)\s*\].*?\[\s*/\s*\1\s*\]",
        flags=re.IGNORECASE | re.DOTALL,
    ),
]
_UNCLOSED_THINKING_AT_START = re.compile(
    r"^\s*(?:<\s*(?:think|thinking|reasoning|analysis)\s*>|\[\s*(?:think|thinking|reasoning|analysis)\s*\]).*",
    flags=re.IGNORECASE | re.DOTALL,
)


def _split_system_messages(messages: list[dict[str, str]]) -> tuple[str | None, list[dict[str, str]]]:
    system_parts = []
    chat_messages = []
    for message in messages:
        role = message.get("role", "user")
        content = str(message.get("content", ""))
        if role == "system":
            system_parts.append(content)
        elif role in {"user", "assistant"}:
            chat_messages.append({"role": role, "content": content})
        else:
            chat_messages.append({"role": "user", "content": content})
    return "\n\n".join(system_parts) if system_parts else None, chat_messages


def _anthropic_generation_params(
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict:
    params = generation_params(temperature=temperature, max_tokens=max_tokens)
    allowed = {"temperature", "max_tokens", "top_p", "top_k"}
    return {key: value for key, value in params.items() if key in allowed}


def _read_error(exc: urllib.error.HTTPError) -> str:
    return exc.read().decode("utf-8", errors="replace")


def strip_thinking_blocks(text: str) -> str:
    cleaned = str(text or "")
    if not STRIP_THINKING_BLOCKS:
        return cleaned.strip()
    previous = None
    while cleaned != previous:
        previous = cleaned
        for pattern in _THINKING_BLOCK_PATTERNS:
            cleaned = pattern.sub("", cleaned)
    cleaned = _UNCLOSED_THINKING_AT_START.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _post_json(url: str, payload: dict, headers: dict[str, str]) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read().decode("utf-8"))


def _openai_compatible_payload(
    messages: list[dict[str, str]],
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_format: dict | None = None,
) -> dict:
    payload = {
        "model": MODEL,
        "messages": messages,
    }
    if response_format:
        payload["response_format"] = response_format
    payload.update(generation_params(temperature=temperature, max_tokens=max_tokens))
    for key, value in OPENAI_EXTRA_BODY.items():
        if key not in {"model", "messages"}:
            payload[key] = value
    return payload


def _openai_compatible_headers(extra_headers: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    if extra_headers:
        headers.update(extra_headers)
    return headers


def _parse_openai_compatible_response(data: dict) -> str:
    choices = data.get("choices", [])
    if not choices:
        return ""
    return strip_thinking_blocks(choices[0].get("message", {}).get("content", ""))


def _normalize_openrouter_payload(payload: dict) -> dict:
    payload = dict(payload)
    reasoning = payload.get("reasoning")
    if isinstance(reasoning, bool):
        payload.pop("reasoning", None)
    elif isinstance(reasoning, str):
        payload["reasoning"] = {"effort": reasoning}
    return payload


def _call_openai_compatible(
    messages: list[dict[str, str]],
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_format: dict | None = None,
) -> str:
    payload = _openai_compatible_payload(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
    )
    headers = _openai_compatible_headers()
    data = _post_json(chat_completions_url(), payload, headers)
    return _parse_openai_compatible_response(data)


def _call_openrouter(
    messages: list[dict[str, str]],
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_format: dict | None = None,
) -> str:
    payload = _openai_compatible_payload(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
    )
    payload = _normalize_openrouter_payload(payload)
    headers = _openai_compatible_headers(
        {
            "HTTP-Referer": OPENROUTER_HTTP_REFERER,
            "X-Title": OPENROUTER_X_TITLE,
        }
    )
    data = _post_json(chat_completions_url(), payload, headers)
    return _parse_openai_compatible_response(data)


def _call_anthropic(
    messages: list[dict[str, str]],
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_format: dict | None = None,
) -> str:
    system, chat_messages = _split_system_messages(messages)
    payload = {
        "model": MODEL,
        "messages": chat_messages,
    }
    if system:
        payload["system"] = system
    payload.update(_anthropic_generation_params(temperature=temperature, max_tokens=max_tokens))

    headers = {
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    if API_KEY:
        headers["x-api-key"] = API_KEY

    data = _post_json(anthropic_messages_url(), payload, headers)
    parts = []
    for block in data.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return strip_thinking_blocks("".join(parts))


def call_llm(
    messages: list[dict[str, str]],
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_format: dict | None = None,
) -> str:
    provider_map = {
        "openai": _call_openai_compatible,
        "anthropic": _call_anthropic,
        "openrouter": _call_openrouter,
    }
    try:
        caller = provider_map.get(API_PROVIDER, _call_openai_compatible)
        return caller(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )
    except urllib.error.HTTPError as exc:
        detail = _read_error(exc)
        raise RuntimeError(f"LLM endpoint returned HTTP {exc.code}: {detail}") from exc
