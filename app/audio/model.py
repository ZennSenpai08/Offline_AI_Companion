"""Offline model verification. Installation is a separate, explicit operation."""
import hashlib
import json
from pathlib import Path
import struct

DEFAULT_MODEL = Path(__file__).resolve().parents[2] / "models" / "ggml-tiny-q5_1.bin"


def verify_model(path: str = "") -> Path:
    model = Path(path).expanduser().resolve() if path else DEFAULT_MODEL
    if not model.is_file():
        raise ValueError(f"Missing multilingual model: {model}. Run scripts/install_speech_model.py first.")
    if ".en" in model.name.lower():
        raise ValueError("English-only .en models cannot recognize Tagalog. Select a multilingual Tiny or Base model.")
    manifest_path = model.with_suffix(model.suffix + ".json")
    if not manifest_path.is_file() or manifest_path.stat().st_size > 16384:
        raise ValueError("Model provenance manifest is missing or too large. Use the speech model installer.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("model") not in ("tiny-q5_1", "base-q5_1") or manifest.get("license") != "MIT":
        raise ValueError("Only verified multilingual Tiny/Base Q5_1 models are enabled in Phase 4.")
    if not 1_000_000 < model.stat().st_size <= 100_000_000 or manifest.get("size") != model.stat().st_size:
        raise ValueError("Model size does not match its manifest.")
    digest = hashlib.sha256()
    with model.open("rb") as stream:
        header = stream.read(12)
        # GGML magic and multilingual vocabulary (English-only has 51864 tokens).
        magic, vocabulary, _ = struct.unpack("<iii", header)
        if magic != 0x67676D6C or vocabulary < 51865:
            raise ValueError("Invalid or English-only whisper.cpp model header.")
        digest.update(header)
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != manifest.get("sha256"):
        raise ValueError("Model SHA-256 does not match its provenance manifest. Reinstall the model.")
    return model
