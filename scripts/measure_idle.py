"""External Windows idle measurement; sampler CPU/RAM excluded from app totals.

Launches a normal app, samples its owned process tree, then posts WM_CLOSE only
to that app's overlay. Does not inject keyboard/mouse input or inspect other apps.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

import psutil


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--animation-fps", type=int, choices=(30, 60), default=30)
    options = parser.parse_args()
    if sys.platform != "win32" or not 10 <= options.seconds <= 3600:
        parser.error("Windows and a duration of 10–3600 seconds are required")
    options.data_dir.mkdir(parents=True, exist_ok=True)
    lock = options.data_dir / "application.lock"
    if lock.exists():
        parser.error("Use an unused data directory (application.lock already exists)")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    child = subprocess.Popen([sys.executable, "-m", "app", "--data-dir", str(options.data_dir), "--animation-fps", str(options.animation_fps)])
    root = psutil.Process(child.pid)
    started = time.perf_counter()
    samples, seen, previous_cpu = [], {}, {}
    previous_time = started
    exit_code = None
    try:
        while time.perf_counter() - started < options.seconds:
            if child.poll() is not None:
                raise RuntimeError(f"App exited early: {child.returncode}")
            now = time.perf_counter()
            private, resident, cpu_delta = 0, 0, 0.0
            processes = [root, *root.children(recursive=True)]
            for process in processes:
                with process.oneshot():
                    key = (process.pid, process.create_time())
                    memory = process.memory_info()
                    times = process.cpu_times()
                    cpu = times.user + times.system
                seen[key] = {"pid": process.pid, "created": key[1], "executable": process.exe()}
                private += memory.private
                resident += memory.rss
                if key in previous_cpu:
                    cpu_delta += max(0.0, cpu - previous_cpu[key])
                previous_cpu[key] = cpu
            samples.append({"seconds": now - started, "private_mib": private / 2**20,
                            "working_set_mib": resident / 2**20, "process_count": len(processes),
                            "cpu_seconds_delta": cpu_delta, "elapsed_seconds": now - previous_time})
            previous_time = now
            time.sleep(max(0, 1 - (time.perf_counter() - now)))
    finally:
        # Scope native close to a window owned by this exact process tree.
        owned_pids = {item[0] for item in seen}
        closed = []
        @callback_type
        def close_overlay(hwnd, _parameter):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in owned_pids:
                title = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, title, len(title))
                if title.value == "Offline Companion — Animated placeholder":
                    closed.append(bool(user32.PostMessageW(hwnd, 0x0010, 0, 0)))
            return True
        user32.EnumWindows(close_overlay, 0)
        try:
            exit_code = child.wait(timeout=10)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Owned app PID {child.pid} did not shut down; use its tray to exit") from exc
    idle = [s for s in samples if s["seconds"] >= 2]
    cpu = 100 * sum(s["cpu_seconds_delta"] for s in idle) / sum(s["elapsed_seconds"] for s in idle)
    def window_median(start, end):
        return statistics.median(s["private_mib"] for s in samples if start <= s["seconds"] < end)
    surviving = []
    for pid, created in seen:
        try:
            if psutil.Process(pid).create_time() == created:
                surviving.append(pid)
        except psutil.NoSuchProcess:
            pass
    report = {"scenario": "normal animated idle; external sampler excluded", "seconds": options.seconds,
              "animation_fps_requested": options.animation_fps,
              "idle_private_mib_median": statistics.median(s["private_mib"] for s in idle),
              "idle_working_set_mib_median": statistics.median(s["working_set_mib"] for s in idle),
              "sampled_peak_private_mib": max(s["private_mib"] for s in samples),
              "sampled_peak_working_set_mib": max(s["working_set_mib"] for s in samples),
              "idle_cpu_one_core_percent": cpu, "idle_cpu_machine_percent": cpu / psutil.cpu_count(),
              "first_window_private_mib": window_median(2, min(32, options.seconds)),
              "last_window_private_mib": window_median(max(2, options.seconds - 30), options.seconds),
              "observed_processes": list(seen.values()), "surviving_owned_pids": surviving,
              "exit_code": exit_code, "native_close_posted": closed, "samples": samples,
              "limits": ["1 second sampling can miss transient peaks/processes.",
                         "Short idle observation cannot prove absence of long-term leaks.",
                         "No in-app instrumentation; no UI latency or first-paint measurement."]}
    options.report.parent.mkdir(parents=True, exist_ok=True)
    options.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "samples"}, indent=2))
    return 0 if exit_code == 0 and not surviving else 1


if __name__ == "__main__":
    raise SystemExit(main())
