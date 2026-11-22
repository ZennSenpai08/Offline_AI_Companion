"""Development-only CPU contention benchmark; no models or inference claims."""
import argparse
import multiprocessing
from pathlib import Path
import sys
import time


def cpu_work(stop):
    value = 1
    while not stop.is_set():
        for _ in range(20000):
            value = (value * 1664525 + 1013904223) & 0xFFFFFFFF


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fps', type=int, choices=(30, 60), default=30)
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--workers', type=int, choices=(1, 2, 3, 4), default=4)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    options = parser.parse_args()
    if not 3 <= options.seconds <= 600:
        parser.error('Duration must be between 3 and 600 seconds')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from app.main import CompanionController
    from app.core.config import SettingsStore
    from app.core.instance import SingleInstance
    from app.performance.probe import DesktopProbe
    import json
    started = time.perf_counter()
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    stop = multiprocessing.Event()
    workers = []
    with SingleInstance(options.data_dir):
        controller = CompanionController(app, SettingsStore(options.data_dir))
        controller.overlay.set_animation_preferences(fps=options.fps)
        probe = DesktopProbe(started, options.seconds, options.report, controller)
        controller.overlay.first_painted.connect(probe.painted)
        controller.overlay.frame_painted.connect(probe.frame_painted)
        try:
            for _ in range(options.workers):
                worker = multiprocessing.Process(target=cpu_work, args=(stop,))
                worker.start(); workers.append(worker)
            probe.start()
            controller.start()
            QTimer.singleShot(options.seconds * 1000, app.quit)
            status = app.exec()
            report = probe.finish()
        finally:
            stop.set()
            for worker in workers:
                worker.join(timeout=5)
                if worker.is_alive():
                    worker.terminate()  # Exact owned handle; never a process-name kill.
                    worker.join(timeout=5)
            controller.close()
        report['scenario'] = 'animated desktop with owned synthetic CPU workers; no AI models'
        report['synthetic_cpu_workers'] = options.workers
        report['worker_exit_codes'] = [worker.exitcode for worker in workers]
        options.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in ('samples', 'limits')}, indent=2))
        return status or int(any(worker.exitcode for worker in workers))


if __name__ == '__main__':
    multiprocessing.freeze_support()
    raise SystemExit(main())
