"""Explicit online installation only; runtime recognition never calls this script."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description="Install an upstream multilingual Whisper Q5_1 model with verified SHA-256")
    parser.add_argument("--model", choices=("tiny", "base"), default="tiny")
    args = parser.parse_args()
    name = f"ggml-{args.model}-q5_1.bin"
    repository = "https://huggingface.co/ggerganov/whisper.cpp"
    # Pin the fetched repository revision before resolving the LFS object.
    with urllib.request.urlopen("https://huggingface.co/api/models/ggerganov/whisper.cpp", timeout=30) as response:
        revision = json.load(response)["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Invalid upstream revision")
    with urllib.request.urlopen(f"{repository}/raw/{revision}/{name}", timeout=30) as response:
        pointer = response.read(4096).decode("ascii")
    digest_match = re.search(r"oid sha256:([0-9a-f]{64})", pointer)
    size_match = re.search(r"size ([0-9]+)", pointer)
    if not digest_match or not size_match:
        raise ValueError("Upstream did not provide the model's LFS SHA-256 and size.")
    expected_hash, expected_size = digest_match[1], int(size_match[1])
    if not 1_000_000 < expected_size <= 100_000_000:
        raise ValueError("Unexpected model size")
    directory = ROOT / "models"
    directory.mkdir(exist_ok=True)
    destination = directory / name
    source = f"{repository}/resolve/{revision}/{name}"
    manifest = {"model": f"{args.model}-q5_1", "sha256": expected_hash, "size": expected_size,
                "revision": revision, "source": source, "license": "MIT",
                "license_source": "https://github.com/ggml-org/whisper.cpp/blob/master/LICENSE",
                "source_model": f"OpenAI Whisper {args.model} multilingual", "quantization": "Q5_1"}
    manifest_path = destination.with_suffix(".bin.json")
    if destination.exists():
        if not manifest_path.exists():
            # Recover an interrupted manifest write only after checking against upstream.
            existing_hash = hashlib.sha256()
            with destination.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    existing_hash.update(block)
            if destination.stat().st_size != expected_size or existing_hash.hexdigest() != expected_hash:
                raise ValueError("Existing model differs from upstream; preserved without alteration.")
            with manifest_path.open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(manifest, indent=2) + "\n")
        from app.audio.model import verify_model
        verify_model(str(destination))
        print(f"Existing verified model preserved: {destination}")
        return
    temporary = destination.with_suffix(".download")
    digest = hashlib.sha256()
    count = 0
    created_temporary = False
    try:
        with temporary.open("xb") as output:
            created_temporary = True
            with urllib.request.urlopen(source, timeout=60) as response:
                while block := response.read(1024 * 1024):
                    count += len(block)
                    if count > expected_size:
                        raise ValueError("Download exceeded declared model size")
                    digest.update(block)
                    output.write(block)
        if count != expected_size or digest.hexdigest() != expected_hash:
            raise ValueError("Downloaded model does not match upstream SHA-256/size")
        temporary.rename(destination)
        with manifest_path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(manifest, indent=2) + "\n")
        from app.audio.model import verify_model
        verify_model(str(destination))
        print(f"Verified {count / 1048576:.2f} MiB: {destination}\nSHA-256: {expected_hash}")
    finally:
        if created_temporary:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Speech model installation failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
