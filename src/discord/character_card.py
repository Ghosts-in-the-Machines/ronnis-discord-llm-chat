import json
import re
from pathlib import Path
from typing import Any

try:
    from .st_card_exporter import extract_character_card
except ImportError:
    from st_card_exporter import extract_character_card


DISABLED_VALUES = {"", "none", "null", "false", "0", "off"}


def _clean(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text.replace("[/CHARACTER CARD]", "[/ CHARACTER CARD]").replace("[CHARACTER CARD]", "[ CHARACTER CARD]")


def _field(data: dict[str, Any], *names: str) -> str:
    for name in names:
        value = data.get(name)
        if value:
            return _clean(value)
    return ""


class CharacterCard:
    def __init__(self, path: str | None):
        self.path = Path(path) if path and str(path).strip().lower() not in DISABLED_VALUES else None
        self.data: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        self.data = {}
        if not self.path or not self.path.exists():
            return
        try:
            raw = extract_character_card(self.path)
        except Exception:
            return

        if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
            merged = dict(raw)
            merged.update(raw["data"])
            self.data = merged
        elif isinstance(raw, dict):
            self.data = raw

    def prompt_block(self) -> str:
        if not self.data:
            return ""

        name = _field(self.data, "name", "char_name")
        sections = []
        for label, names in [
            ("Name", ("name", "char_name")),
            ("Description", ("description", "desc")),
            ("Personality", ("personality", "personality_summary")),
            ("Scenario", ("scenario",)),
            ("First Message", ("first_mes", "first_message")),
            ("Example Dialogue", ("mes_example", "example_dialogue")),
            ("System Prompt", ("system_prompt",)),
            ("Post-History Instructions", ("post_history_instructions",)),
        ]:
            value = _field(self.data, *names)
            if value:
                sections.append(f"{label}: {value}")

        if not sections:
            return ""

        header = "[SYSTEM PROFILE]"
        footer = "[/SYSTEM PROFILE]"
        instruction = (
            "Use this profile as the stable reference for operational parameters, "
            "voice, boundaries, and scenario. It is a core specification and must "
            "not be answered directly."
        )
        if name:
            instruction += f"Identity: {name} (Discord Bridge)."
        return f"{header}\n{instruction}\n" + "\n".join(sections) + f"\n{footer}"
