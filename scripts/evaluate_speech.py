"""Offline, repeatable recorded-speech WER/CER. No transcript is fed to the model."""
import argparse
import json
from pathlib import Path
import sys
from threading import Event

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.audio.config import AudioSettings
from app.audio.evaluation import read_pcm, score
from app.audio.model import verify_model
from app.audio.recognizer import Recognizer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--model", default="")
    parser.add_argument("--language", choices=("auto", "en", "tl"), default="auto")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    model = verify_model(args.model)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    cases = manifest["cases"]
    if not 1 <= len(cases) <= 100:
        raise ValueError("Use 1–100 reference recordings per evaluation.")
    results = []
    settings = AudioSettings(model_path=str(model), language=args.language)
    cancel = Event()
    try:
        for case in cases:
            if type(case.get("synthetic")) is not bool or not case.get("source"):
                raise ValueError("Each case must explicitly identify source and synthetic true/false.")
            pcm = read_pcm(args.manifest.parent / case["file"])
            result = Recognizer().transcribe(pcm, settings, cancel)
            result.update(score(case["reference"], result["text"]))
            result.update(file=case["file"], reference=case["reference"], language=case["language"],
                          source=case["source"], synthetic=case["synthetic"])
            results.append(result)
            print(f"{case['file']}: WER={result['wer']:.3f}, CER={result['cer']:.3f}, latency={result['latency_seconds']:.3f}s")
    finally:
        cancel.set()
    groups = {}
    for language in {item['language'] for item in results}:
        group = [item for item in results if item['language'] == language]
        groups[language] = {"wer": sum(item['word_errors'] for item in group) / sum(item['reference_words'] for item in group),
                            "cer": sum(item['character_errors'] for item in group) / sum(item['reference_characters'] for item in group)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"model": str(model), "language_hint": args.language,
        "normalization": "NFKC, casefold, remove punctuation; CER excludes spaces", "groups": groups,
        "cases": results}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Recognition evaluation failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
