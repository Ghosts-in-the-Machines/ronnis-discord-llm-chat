import argparse
import base64
import json
import struct
import zlib
from pathlib import Path
from typing import Any


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class CharacterCardError(ValueError):
    pass


def _decode_text_chunk(chunk_type: bytes, payload: bytes) -> tuple[str, str] | None:
    if chunk_type == b"tEXt":
        if b"\x00" not in payload:
            return None
        keyword, text = payload.split(b"\x00", 1)
        return keyword.decode("latin-1", errors="replace"), text.decode("latin-1", errors="replace")

    if chunk_type == b"zTXt":
        if b"\x00" not in payload:
            return None
        keyword, rest = payload.split(b"\x00", 1)
        if not rest:
            return None
        compression_method = rest[0]
        if compression_method != 0:
            return None
        text = zlib.decompress(rest[1:]).decode("latin-1", errors="replace")
        return keyword.decode("latin-1", errors="replace"), text

    if chunk_type == b"iTXt":
        parts = payload.split(b"\x00", 5)
        if len(parts) != 6:
            return None
        keyword, compression_flag, compression_method, _language, _translated, text = parts
        if compression_flag == b"\x01":
            if compression_method != b"\x00":
                return None
            text = zlib.decompress(text)
        return keyword.decode("latin-1", errors="replace"), text.decode("utf-8", errors="replace")

    return None


def read_png_text_chunks(path: str | Path) -> dict[str, str]:
    card_path = Path(path)
    with card_path.open("rb") as handle:
        if handle.read(len(PNG_SIGNATURE)) != PNG_SIGNATURE:
            raise CharacterCardError(f"{card_path} is not a PNG file")

        chunks: dict[str, str] = {}
        while True:
            length_bytes = handle.read(4)
            if not length_bytes:
                break
            if len(length_bytes) != 4:
                raise CharacterCardError("Invalid PNG chunk length")
            length = struct.unpack(">I", length_bytes)[0]
            chunk_type = handle.read(4)
            payload = handle.read(length)
            handle.read(4)

            decoded = _decode_text_chunk(chunk_type, payload)
            if decoded:
                keyword, text = decoded
                chunks[keyword] = text
            if chunk_type == b"IEND":
                break
        return chunks


def _json_from_chara(value: str) -> dict[str, Any]:
    raw = value.strip()
    candidates = [raw]
    try:
        decoded = base64.b64decode(raw, validate=True).decode("utf-8")
        candidates.insert(0, decoded)
    except Exception:
        pass

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise CharacterCardError("PNG chara metadata was found, but it was not valid card JSON")


def extract_character_card(path: str | Path) -> dict[str, Any]:
    card_path = Path(path)
    if card_path.suffix.lower() == ".json":
        data = json.loads(card_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise CharacterCardError("Character card JSON must be an object")
        return data

    chunks = read_png_text_chunks(card_path)
    for key in ("chara", "Chara", "CHARA"):
        if key in chunks:
            return _json_from_chara(chunks[key])
    raise CharacterCardError("No SillyTavern chara metadata found in PNG")


def export_character_card(input_path: str | Path, output_path: str | Path | None = None) -> Path:
    source = Path(input_path)
    target = Path(output_path) if output_path else source.with_suffix(".json")
    data = extract_character_card(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Export SillyTavern PNG character card metadata to JSON.")
    parser.add_argument("input", help="Path to a SillyTavern .png character card or .json card.")
    parser.add_argument("-o", "--output", help="Output JSON path. Defaults to input path with .json suffix.")
    args = parser.parse_args()

    try:
        output = export_character_card(args.input, args.output)
    except Exception as exc:
        print(f"[ST CARD] Export failed: {exc}")
        return 1

    print(f"[ST CARD] Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
