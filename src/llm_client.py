import json
import urllib.error
import urllib.request

from config import (
    API_KEY,
    API_PROVIDER,
    MODEL,
    OPENROUTER_HTTP_REFERER,
    OPENROUTER_X_TITLE,
    anthropic_messages_url,
    chat_completions_url,
    generation_params,
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
) -> dict:
    payload = {
        "model": MODEL,
        "messages": messages,
    }
    payload.update(generation_params(temperature=temperature, max_tokens=max_tokens))
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
    return str(choices[0].get("message", {}).get("content", "")).strip()


def _call_openai_compatible(
    messages: list[dict[str, str]],
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    payload = _openai_compatible_payload(messages, temperature=temperature, max_tokens=max_tokens)
    headers = _openai_compatible_headers()
    data = _post_json(chat_completions_url(), payload, headers)
    return _parse_openai_compatible_response(data)


def _call_openrouter(
    messages: list[dict[str, str]],
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    payload = _openai_compatible_payload(messages, temperature=temperature, max_tokens=max_tokens)
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
    return "".join(parts).strip()


def call_llm(
    messages: list[dict[str, str]],
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    provider_map = {
        "openai": _call_openai_compatible,
        "anthropic": _call_anthropic,
        "openrouter": _call_openrouter,
    }
    try:
        caller = provider_map.get(API_PROVIDER, _call_openai_compatible)
        return caller(messages, temperature=temperature, max_tokens=max_tokens)
    except urllib.error.HTTPError as exc:
        detail = _read_error(exc)
        raise RuntimeError(f"LLM endpoint returned HTTP {exc.code}: {detail}") from exc
