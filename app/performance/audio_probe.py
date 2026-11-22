"""Opt-in all-owned-process sampler, off the GUI thread. Not a runtime service."""
from collections import deque
import os
from pathlib import Path
import statistics
import sys
from threading import Event, Thread
import time
import psutil
from app.core.process_job import ProcessJob


class AudioProbe:
    def __init__(self, phase):
        self.phase = phase
        self.root = psutil.Process()
        parent = self.root.parent()
        if os.name == "nt" and parent:
            try:
                if Path(parent.exe()).resolve() == Path(sys.executable).resolve() and parent.cmdline()[1:] == self.root.cmdline()[1:]:
                    self.root = parent
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        self.started = time.perf_counter()
        self.stop = Event()
        self.thread = Thread(target=self._run, name="audio-benchmark-sampler", daemon=True)
        self.samples = deque(maxlen=10000)
        self.seen = {}
        self.read_failures = 0

    def start(self): self.thread.start()

    def _run(self):
        previous = {}
        previous_time = self.started
        processes = {}
        while not self.stop.is_set():
            now = time.perf_counter()
            try:
                pids = {self.root.pid, os.getpid()} | ProcessJob.owned_process_ids()
                for pid in pids - processes.keys():
                    try:
                        processes[pid] = psutil.Process(pid)
                    except psutil.NoSuchProcess:
                        self.read_failures += 1
                processes = {pid: process for pid, process in processes.items() if pid in pids}
            except OSError:
                self.read_failures += 1
            private = resident = count = 0
            cpu_delta = 0.0
            for process in processes.values():
                try:
                    with process.oneshot():
                        key = (process.pid, process.create_time())
                        memory = process.memory_info()
                        cpu = process.cpu_times()
                        total = cpu.user + cpu.system
                    # Count startup CPU for workers born during this measurement.
                    baseline = previous.get(key, 0 if process.create_time() >= time.time() - (now - self.started) else total)
                    cpu_delta += max(0, total - baseline)
                    previous[key] = total
                    self.seen[key] = {"pid": process.pid, "created": key[1]}
                    private += getattr(memory, "private", 0)
                    resident += memory.rss
                    count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    self.read_failures += 1
            self.samples.append({"seconds": now - self.started, "phase": self.phase(), "private_mib": private / 2**20,
                "resident_mib": resident / 2**20, "processes": count, "cpu_seconds": cpu_delta,
                "elapsed": now - previous_time})
            previous_time = now
            self.stop.wait(max(.001, .1 - (time.perf_counter() - now)))

    def finish(self):
        self.stop.set()
        self.thread.join(5)
        if self.thread.is_alive(): raise RuntimeError("Benchmark sampler failed to stop")
        samples = list(self.samples)
        groups = {}
        for phase in sorted({sample["phase"] for sample in samples}):
            subset = [sample for sample in samples if sample["phase"] == phase]
            elapsed = sum(sample["elapsed"] for sample in subset)
            cpu = 100 * sum(sample["cpu_seconds"] for sample in subset) / elapsed if elapsed else 0
            groups[phase] = {"median_private_mib": statistics.median(s["private_mib"] for s in subset),
                "median_resident_mib": statistics.median(s["resident_mib"] for s in subset),
                "peak_private_mib": max(s["private_mib"] for s in subset),
                "peak_resident_mib": max(s["resident_mib"] for s in subset),
                "cpu_percent_one_core": cpu, "cpu_percent_machine": cpu / (psutil.cpu_count() or 1)}
        return {"groups": groups, "processes": list(self.seen.values()), "read_failures": self.read_failures,
                "samples": samples, "discovery": "GUI + matching venv launcher + native PID lists of every active application-owned Job Object",
                "limitations": "Instrumented totals include sampler overhead. 100 ms memory/Job PID sampling can miss transient peaks/final CPU. Future workers must use ProcessJob to be counted. RSS can double-count shared pages. No DWM/GPU allocation accounting."}
