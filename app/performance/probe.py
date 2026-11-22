from __future__ import annotations

from collections import deque
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import time

import psutil
from PySide6.QtCore import QObject, QTimer, Qt, qVersion
from PySide6.QtWidgets import QApplication


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


class DesktopProbe(QObject):
    """Includes the Windows venv redirector and descendants, not the shell."""

    def __init__(self, started_at: float, seconds: float, output: Path, parent: QObject):
        super().__init__(parent)
        self.started_at = started_at
        self.seconds = seconds
        self.output = output
        self.process = psutil.Process()
        self.root = self.process
        # CPython's Windows venv executable waits for the real interpreter.
        # Count that owned parent, but never count an unrelated invoking shell.
        parent_process = self.process.parent()
        if sys.platform == "win32" and sys.prefix != sys.base_prefix and parent_process:
            try:
                if (Path(parent_process.exe()).resolve() == Path(sys.executable).resolve()
                        and parent_process.cmdline()[1:] == self.process.cmdline()[1:]
                        and parent_process.exe() != self.process.exe()):
                    self.root = parent_process
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        self.processes = [self.process]
        self.next_tree_scan = 0.0
        self.samples: deque[dict] = deque(maxlen=6100)
        self.heartbeats: deque[float] = deque(maxlen=40000)
        self.frames: deque[tuple[float, float]] = deque(maxlen=40000)
        self.seen: set[tuple[int, float]] = set()
        self.previous_cpu: dict[tuple[int, float], float] = {}
        self.previous_sample = time.perf_counter()
        self.previous_heartbeat = self.previous_sample
        self.first_paint_ms: float | None = None
        self.first_paint_from_creation_ms: float | None = None
        self.read_failures = 0
        self.sample_timer = QTimer(self)
        self.sample_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.sample_timer.setInterval(100)
        self.sample_timer.timeout.connect(self.sample)
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.heartbeat_timer.setInterval(16)
        self.heartbeat_timer.timeout.connect(self.heartbeat)

    def start(self) -> None:
        self.sample()
        self.sample_timer.start()
        self.heartbeat_timer.start()

    def painted(self) -> None:
        if self.first_paint_ms is None:
            self.first_paint_ms = (time.perf_counter() - self.started_at) * 1000
            self.first_paint_from_creation_ms = (time.time() - self.process.create_time()) * 1000

    def heartbeat(self) -> None:
        now = time.perf_counter()
        self.heartbeats.append(max(0.0, (now - self.previous_heartbeat) * 1000 - 16))
        self.previous_heartbeat = now

    def frame_painted(self, paint_ms: float) -> None:
        elapsed = time.perf_counter() - self.started_at
        if elapsed >= 2:
            self.frames.append((elapsed, paint_ms))

    def sample(self) -> None:
        now = time.perf_counter()
        elapsed = max(now - self.previous_sample, 1e-6)
        private, resident, cpu_delta, count = 0, 0, 0.0, 0
        private_available = True
        lifetime_peak_resident = 0
        lifetime_peak_commit = 0
        # Tree discovery costs ~32 ms on the validation machine. Keep cheap
        # memory/CPU samples at 100 ms, but discover descendants every 5 seconds.
        if now >= self.next_tree_scan:
            try:
                self.processes = [self.root, *self.root.children(recursive=True)]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.processes = [self.process]
                self.read_failures += 1
            self.next_tree_scan = now + 5.0
        for process in self.processes:
            try:
                with process.oneshot():
                    key = (process.pid, process.create_time())
                    memory = process.memory_info()
                    times = process.cpu_times()
                    cpu = times.user + times.system
                self.seen.add(key)
                count += 1
                resident += memory.rss
                if hasattr(memory, "private"):
                    private += memory.private
                else:
                    private_available = False
                if process.pid == os.getpid():
                    lifetime_peak_resident = getattr(memory, "peak_wset", 0)
                    lifetime_peak_commit = getattr(memory, "peak_pagefile", 0)
                if key in self.previous_cpu:
                    cpu_delta += max(0, cpu - self.previous_cpu[key])
                self.previous_cpu[key] = cpu
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.read_failures += 1
        self.samples.append({
            "seconds": now - self.started_at, "private_bytes": private if private_available else None,
            "working_set_bytes": resident, "processes": count,
            "cpu_seconds_delta": cpu_delta, "sample_elapsed_seconds": elapsed,
            "cpu_percent_one_core": cpu_delta / elapsed * 100,
            "cpu_percent_machine": cpu_delta / elapsed * 100 / (psutil.cpu_count() or 1),
            "main_lifetime_peak_working_set_bytes": lifetime_peak_resident,
            "main_lifetime_peak_commit_bytes": lifetime_peak_commit,
        })
        self.previous_sample = now

    def finish(self) -> dict:
        self.sample_timer.stop()
        self.heartbeat_timer.stop()
        self.sample()
        samples = list(self.samples)
        idle = [s for s in samples if s["seconds"] >= 2.0]
        idle_elapsed = sum(s["sample_elapsed_seconds"] for s in idle)
        idle_cpu = sum(s["cpu_seconds_delta"] for s in idle) / idle_elapsed * 100 if idle_elapsed else None
        def median_mib(field: str):
            values = [s[field] / 2**20 for s in idle if s[field] is not None]
            return statistics.median(values) if values else None
        def peak_mib(field: str):
            values = [s[field] / 2**20 for s in samples if s[field] is not None]
            return max(values) if values else None
        app = QApplication.instance()
        frames = list(self.frames)
        intervals = [(b[0] - a[0]) * 1000 for a, b in zip(frames, frames[1:])]
        settings = self.parent().settings
        report = {
            "schema": 4, "phase": 4, "scenario": "instrumented animated desktop with microphone status panel",
            "microphone_enabled_at_finish": getattr(self.parent(), "microphone_enabled", False),
            "animation_fps_requested": settings.animation_fps,
            "animation_intensity": settings.animation_intensity, "reduced_motion": settings.reduced_motion,
            "paint_fps_measured": (len(frames) - 1) / (frames[-1][0] - frames[0][0]) if len(frames) > 1 else None,
            "frame_interval_ms_p95": percentile(intervals, .95),
            "frame_interval_ms_max": max(intervals, default=None),
            "paint_duration_ms_p95": percentile([f[1] for f in frames], .95),
            "painted_frames_after_warmup": len(frames),
            "platform": platform.platform(), "python": platform.python_version(), "qt": qVersion(),
            "qt_platform": app.platformName(), "cpu": platform.processor(),
            "logical_cpus": psutil.cpu_count(), "system_ram_gib": psutil.virtual_memory().total / 2**30,
            "duration_seconds": time.perf_counter() - self.started_at,
            "sampling_interval_ms": 100, "process_tree_interval_seconds": 5, "warmup_excluded_seconds": 2,
            "startup_entry_to_first_paint_ms": self.first_paint_ms,
            "startup_process_creation_to_first_paint_ms": self.first_paint_from_creation_ms,
            "idle_private_mib_median": median_mib("private_bytes"),
            "idle_working_set_mib_median": median_mib("working_set_bytes"),
            "sampled_peak_private_mib": peak_mib("private_bytes"),
            "sampled_peak_working_set_mib": peak_mib("working_set_bytes"),
            "main_lifetime_peak_working_set_mib": peak_mib("main_lifetime_peak_working_set_bytes"),
            "main_lifetime_peak_commit_mib": peak_mib("main_lifetime_peak_commit_bytes"),
            "idle_cpu_one_core_percent_mean": idle_cpu,
            "idle_cpu_machine_percent_mean": idle_cpu / (psutil.cpu_count() or 1) if idle_cpu is not None else None,
            "event_loop_lateness_ms_p95": percentile(list(self.heartbeats), 0.95),
            "event_loop_lateness_ms_max": max(self.heartbeats, default=None),
            "observed_processes": [{"pid": pid, "created": created} for pid, created in sorted(self.seen)],
            "process_read_failures": self.read_failures,
            "screens": [{"name": s.name(), "dpr": s.devicePixelRatio(), "logical_dpi": s.logicalDotsPerInch(), "work_area": list(s.availableGeometry().getRect())} for s in app.screens()],
            "limits": ["Instrumentation adds 100 ms sampling, 5 second process discovery and a 16 ms heartbeat.", "Paint FPS counts QWidget paints, not physical display presentation; event-loop lateness is not visual drag latency.", "Sub-100 ms peaks and descendants shorter than 5 seconds may be missed; use benchmark_microphone.py/benchmark_speech.py for audio worker measurements.", "Includes matching Windows venv launcher parent; excludes invoking shell.", "GPU/compositor memory not measured. Microphone finish state alone does not prove physical capture or recognition occurred.", "Working-set sum may count shared pages more than once."],
            "samples": samples,
        }
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        return report
