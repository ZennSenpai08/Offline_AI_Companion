"""Cancellable, single-request whisper.cpp process owner; called off the Qt thread."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import sysconfig
import time
from threading import Thread
from app.core.process_job import ProcessJob


class Cancelled(Exception):
    pass


class Recognizer:
    def __init__(self):
        self.process = None

    def transcribe(self, pcm, settings, cancel):
        if cancel.is_set():
            raise Cancelled()
        if not 3200 <= len(pcm) <= 800000 or len(pcm) % 2:
            raise ValueError("Recognition audio must be 0.1–25 seconds of mono 16 kHz s16 PCM.")
        job = ProcessJob()
        process = None
        io_thread = None
        started = time.perf_counter()
        try:
            environment = os.environ.copy()
            environment.update(OMP_NUM_THREADS=str(settings.threads), OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
            # Windows venv python.exe is a redirector that could spawn before Job assignment.
            # Launch the real interpreter directly with ONLY this venv's site-packages.
            bootstrap = "import sys,runpy; sys.path.insert(0,sys.argv.pop(1)); runpy.run_module('app.audio.worker',run_name='__main__')"
            command = [getattr(sys, "_base_executable", sys.executable), "-S", "-c", bootstrap,
                       sysconfig.get_path("purelib"), settings.model_path, str(settings.threads), settings.language]
            process = subprocess.Popen(
                command,
                cwd=Path(__file__).resolve().parents[2], env=environment,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                # No console or hidden conhost.exe; all three standard handles are explicit.
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
            )
            self.process = process
            job.assign(process)
            # A pipe write can block if a worker stalls before reading. Keep even that
            # write off the cancellation coordinator so mute can always close the Job.
            response = {}
            def exchange():
                try:
                    response["output"], _ = process.communicate(struct.pack("<I", len(pcm)) + pcm)
                except Exception as exc:
                    response["error"] = exc
            io_thread = Thread(target=exchange, name="recognition-pipe", daemon=True)
            io_thread.start()
            while True:
                if cancel.is_set():
                    raise Cancelled()
                if time.perf_counter() - started > 120:
                    raise RuntimeError("Recognition exceeded 120 seconds. Try Tiny or a shorter utterance.")
                io_thread.join(.05)
                if not io_thread.is_alive():
                    break
            if "error" in response:
                raise RuntimeError("Recognition pipe failed.") from response["error"]
            output = response["output"]
            if len(output) > 65536:
                raise RuntimeError("Recognition response exceeded its bound.")
            if cancel.is_set():
                raise Cancelled()
            try:
                result = json.loads(output)
            except (ValueError, UnicodeError):
                raise RuntimeError(f"Recognition worker exited without a valid response (code {process.returncode}).") from None
            if "error" in result or process.returncode:
                raise RuntimeError(result.get("error", "Recognition worker failed."))
            result["latency_seconds"] = time.perf_counter() - started
            return result
        finally:
            job.close()  # Includes any descendants assigned to this owned Job.
            if process is not None:
                if process.poll() is None:
                    process.kill()  # This exact Popen handle only, never a process-name search.
                if io_thread is not None:
                    io_thread.join(5)
                    if io_thread.is_alive():
                        raise RuntimeError("Owned recognition pipe did not close after worker termination.")
                else:
                    process.communicate(timeout=5)
            self.process = None
