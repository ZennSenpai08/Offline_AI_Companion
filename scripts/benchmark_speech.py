"""Measure local WAV inference alongside the animated overlay; label audio provenance."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import tempfile
from threading import Event, Thread
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from app.audio.config import AudioSettings
from app.audio.evaluation import read_pcm
from app.audio.model import verify_model
from app.audio.recognizer import Recognizer, Cancelled
from app.core.config import SettingsStore
from app.main import CompanionController
from app.performance.audio_probe import AudioProbe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path)
    parser.add_argument("--model", default="")
    parser.add_argument("--repeats", type=int, choices=range(1, 6), default=3)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source-kind", choices=("human-recording", "synthetic-fixture", "unspecified"), default="unspecified")
    args = parser.parse_args()
    model = verify_model(args.model)
    pcm = read_pcm(args.wav)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    cancel, done = Event(), Event()
    phase, results, failures, frames = ["baseline"], [], [], []
    with tempfile.TemporaryDirectory(prefix="companion-speech-benchmark-") as directory:
        controller = CompanionController(app, SettingsStore(Path(directory)))
        probe = AudioProbe(lambda: phase[0])
        controller.overlay.frame_painted.connect(lambda _duration: frames.append((time.perf_counter(), phase[0])))
        def work():
            try:
                if cancel.wait(3): return
                for index in range(args.repeats):
                    phase[0] = f"recognition-{index + 1}"
                    result = Recognizer().transcribe(pcm, AudioSettings(model_path=str(model)), cancel)
                    results.append({k: v for k, v in result.items() if k != "text"})
                    phase[0] = f"recovery-{index + 1}"
                    if cancel.wait(5): return
            except Cancelled:
                failures.append("Cancelled")
            except Exception as exc:
                failures.append(str(exc))
            finally:
                done.set()
        worker = Thread(target=work, name="recorded-speech-benchmark", daemon=True)
        timer = QTimer()
        def update():
            controller.mic_panel.status.setText("Recorded audio test: " + phase[0])
            if done.is_set(): app.quit()
        timer.timeout.connect(update)
        timer.start(100)
        app.aboutToQuit.connect(cancel.set)
        controller.start()
        probe.start()
        worker.start()
        app.exec()
        cancel.set()
        worker.join(6)
        timer.stop()
        controller.close()
        report = probe.finish()
        report.update(scenario="Local WAV replay into real whisper.cpp; microphone NOT opened", source_kind=args.source_kind, wav=str(args.wav),
                      model=str(model), results=results, errors=failures, worker_stopped=not worker.is_alive())
        for key, group in report["groups"].items():
            stamps = [stamp for stamp, phase_name in frames if phase_name == key]
            intervals = sorted((b - a) * 1000 for a, b in zip(stamps, stamps[1:]))
            group["paint_fps"] = (len(stamps) - 1) / (stamps[-1] - stamps[0]) if len(stamps) > 1 else None
            group["interval_p95_ms"] = intervals[min(len(intervals) - 1, int(len(intervals) * .95))] if intervals else None
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return 2 if failures or worker.is_alive() else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Speech benchmark failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
