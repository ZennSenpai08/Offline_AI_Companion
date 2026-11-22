"""Explicit-consent live microphone benchmark. No audio or transcripts are saved."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from app.audio.config import AudioSettings
from app.audio.service import AudioService
from app.core.config import SettingsStore
from app.main import CompanionController
from app.performance.audio_probe import AudioProbe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consent-to-microphone", required=True, action="store_true")
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--model", default="")
    parser.add_argument("--device", default="")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not 10 <= args.seconds <= 600:
        parser.error("Duration must be 10–600 seconds")
    settings = AudioSettings(consent=True, device=args.device, model_path=args.model)
    AudioService._preflight(settings)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    frames, latencies, errors = [], {}, set()
    with tempfile.TemporaryDirectory(prefix="companion-microphone-benchmark-") as directory:
        controller = CompanionController(app, SettingsStore(Path(directory)))
        controller.settings.audio = settings
        probe = AudioProbe(lambda: controller.audio.snapshot()["status"])
        def frame(_duration):
            state = controller.audio.snapshot()
            frames.append((time.perf_counter(), state["status"]))
            if state["latency_seconds"] is not None and state["text"]:
                latencies[state["turn"]] = state["latency_seconds"]
            if state["status"] in ("Recognition Error", "Device Unavailable"):
                errors.add(state["detail"])
        controller.overlay.frame_painted.connect(frame)
        controller.start()
        probe.start()
        controller.set_microphone(True)
        QTimer.singleShot(args.seconds * 1000, app.quit)
        app.exec()
        controller.close()
        report = probe.finish()
        for phase, group in report["groups"].items():
            intervals = [b[0] - a[0] for a, b in zip(frames, frames[1:]) if a[1] == b[1] == phase]
            group["paint_fps"] = len(intervals) / sum(intervals) if intervals else None
        report.update(scenario="Physical microphone capture with explicit CLI consent",
                      raw_audio_saved=False, transcripts_saved=False, latency_seconds=list(latencies.values()),
                      errors=sorted(errors), audio_thread_stopped=not controller.audio.thread.is_alive())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return 2 if errors else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Microphone benchmark failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
