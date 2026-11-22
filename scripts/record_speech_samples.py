"""Explicitly retained, human-recorded evaluation corpus. Not ordinary runtime capture."""
import argparse
import json
from pathlib import Path
import sys
from threading import Event
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.audio.capture import Capture
from app.audio.config import AudioSettings

PHRASES = [
    ("tagalog", "Kamusta ka?"), ("tagalog", "Anong ginagawa mo?"),
    ("tagalog", "Pwede mo ba akong tulungan?"), ("taglish", "Can you help me sa project ko?"),
    ("tagalog", "Ang hirap naman nito."), ("taglish", "Explain mo nga kung paano ito gumagana."),
    ("tagalog", "Awit, ang hirap ng assignment."), ("english", "What is machine learning?")]


def main():
    parser = argparse.ArgumentParser(description="Record eight real speech samples locally for Phase 4 accuracy testing")
    parser.add_argument("--consent-and-retain-audio", action="store_true", required=True,
                        help="Explicit consent to microphone capture AND saving these test WAV files")
    parser.add_argument("--output", type=Path, default=ROOT / ".runtime" / "speech-samples")
    parser.add_argument("--device", default="", help="Exact host API | input name from check_audio.py")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        raise ValueError("Choose an empty output directory; existing recordings are preserved.")
    print("These eight WAV files will remain in", args.output.resolve())
    print("Nothing is uploaded. Close other microphone apps first. Ctrl+C cancels and releases capture.")
    cases = []
    for index, (language, reference) in enumerate(PHRASES, 1):
        input(f"\n{index}/8: {reference}\nPress Enter when ready; speak after RECORDING appears. ")
        cancel = Event()
        capture = Capture(AudioSettings(consent=True, device=args.device), cancel)
        pcm = bytearray()
        try:
            print("RECORDING — speak now (6 seconds)", flush=True)
            deadline = time.monotonic() + 8
            while len(pcm) < 6 * 32000 and time.monotonic() < deadline:
                for frame in capture.read():
                    pcm.extend(frame)
            if len(pcm) < 6 * 32000:
                raise RuntimeError("Microphone did not supply six seconds of PCM.")
        finally:
            cancel.set()
            capture.close()
        filename = f"{index:02d}-{language}.wav"
        with wave.open(str(args.output / filename), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(pcm[:6 * 32000])
        cases.append({"file": filename, "reference": reference, "language": language,
                      "source": "human microphone recording", "synthetic": False})
        (args.output / "manifest.json").write_text(json.dumps({"cases": cases}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Saved; microphone released.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Recording failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
