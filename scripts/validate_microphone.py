"""Opt-in physical input test through the actual Qt controls; saves no audio/text."""
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
from app.audio.capture import Capture
from app.audio.config import AudioSettings
from app.audio.service import AudioService
from app.core.config import SettingsStore
from app.main import CompanionController


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consent-to-microphone", action="store_true", required=True)
    parser.add_argument("--device", default="")
    parser.add_argument("--cycles", type=int, choices=range(1, 21), default=6)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    settings = AudioSettings(consent=True, device=args.device)
    AudioService._preflight(settings)
    captures, results, errors = [], [], []

    class ObservedCapture(Capture):
        def __init__(self, *a, **kw):
            self.callbacks = 0
            super().__init__(*a, **kw)
            self.native_stream = self.stream
            captures.append(self)

        def _callback(self, *a):
            self.callbacks += 1
            return super()._callback(*a)

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    with tempfile.TemporaryDirectory(prefix="companion-physical-input-") as directory:
        controller = CompanionController(app, SettingsStore(Path(directory)))
        controller.settings.audio = settings
        controller.audio.capture_factory = ObservedCapture
        phase, changed, counts, start_index = "enable", time.monotonic(), [], 0
        timer = QTimer()

        def step():
            nonlocal phase, changed, counts, start_index
            try:
                now = time.monotonic()
                state = controller.audio.snapshot()
                if state["status"] in ("Device Unavailable", "Recognition Error"):
                    raise RuntimeError(state["detail"])
                if now - changed > 10:
                    raise RuntimeError(f"Timed out during {phase}: {state['status']}")
                if phase == "enable":
                    start_index = len(captures)
                    controller.controls.mic_action.trigger()
                    phase, changed = "capture", now
                elif phase == "capture" and len(captures) > start_index and now - changed > 1:
                    if sum(c.callbacks for c in captures[start_index:]) < 5:
                        raise RuntimeError("Native stream did not deliver enough callbacks")
                    if len(results) % 2:
                        controller.controls.mic_action.trigger()
                    else:
                        controller.mic_panel.toggle.click()
                    phase, changed = "disable", now
                elif phase == "disable" and state["status"] == "Microphone Disabled":
                    current = captures[start_index:]
                    if not all(c.native_stream.closed and c.stream is None and c.queue.empty() and not c.pending for c in current):
                        raise RuntimeError("Mute did not close all native streams and clear buffers")
                    counts = [c.callbacks for c in current]
                    results.append({"cycle": len(results) + 1, "off_control": "tray" if len(results) % 2 else "panel",
                        "disable_ms": (now - changed) * 1000, "callback_counts": counts,
                        "capture_rates": [c.rate for c in current], "native_handles_closed": True,
                        "buffers_empty": True})
                    phase, changed = "verify_off", now
                elif phase == "verify_off" and now - changed > .3:
                    if counts != [c.callbacks for c in captures[start_index:]]:
                        raise RuntimeError("Audio callbacks continued after confirmed mute")
                    results[-1]["no_callbacks_after_off"] = True
                    if len(results) >= args.cycles:
                        app.quit()
                    else:
                        phase, changed = "enable", now
            except Exception as exc:
                errors.append(str(exc))
                app.quit()

        timer.timeout.connect(step)
        controller.start()
        timer.start(20)
        app.exec()
        timer.stop()
        controller.close()
        report = {"scenario": "Actual microphone callbacks and native stream closure through Qt tray/panel controls",
                  "device": args.device or "system default", "cycles": results, "errors": errors,
                  "audio_saved": False, "transcripts_saved": False,
                  "coordinator_stopped": controller.audio.thread is None or not controller.audio.thread.is_alive(),
                  "streams_opened": len(captures),
                  "all_native_streams_closed": all(c.native_stream.closed for c in captures) if captures else None}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 2 if errors or len(results) != args.cycles else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Physical input validation failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
