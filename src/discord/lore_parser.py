import json
import re
from pathlib import Path
from typing import Iterable


class Lorebook:
    def __init__(self, path: str | None = "lorebooks"):
        self.enabled = path is not None and str(path).strip().lower() not in {"", "none", "null", "false", "0", "off"}
        self.path = Path(path) if self.enabled else None
        self.entries: list[tuple[str, str]] = []
        self.reload()

    def reload(self) -> None:
        self.entries = []
        if not self.enabled or self.path is None or not self.path.exists():
            return

        for file_path in sorted(self.path.glob("*.json")):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            self._load_entry(data)

    def _load_entry(self, data: object) -> None:
        if isinstance(data, list):
            for item in data:
                self._load_entry(item)
            return
        if not isinstance(data, dict):
            return

        keys = data.get("keys", [])
        content = str(data.get("content", "")).strip()
        if not content:
            return

        for key in self._iter_keys(keys):
            self.entries.append((key.lower(), content))

    @staticmethod
    def _iter_keys(keys: object) -> Iterable[str]:
        if isinstance(keys, str):
            keys = [keys]
        if not isinstance(keys, list):
            return []
        return [str(key).strip() for key in keys if str(key).strip()]

    def query(self, text: str) -> str:
        haystack = str(text or "").lower()
        if not haystack:
            return ""

        matched = []
        seen = set()
        for key, content in self.entries:
            if key in haystack and content not in seen:
                seen.add(content)
                matched.append(content)

        if not matched:
            return ""

        wrapped = []
        for item in matched:
            safe = re.sub(r"\s+", " ", item).strip()
            wrapped.append(f"[SUPPLEMENTAL CONTEXT]\n{safe}\n[/SUPPLEMENTAL CONTEXT]")
        return "\n\n".join(wrapped)
