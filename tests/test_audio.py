"""Synthetic PCM/device tests, explicitly not physical microphone/ASR quality tests."""
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
from queue import Queue, Empty
import struct
import subprocess
import sys
import tempfile
from threading import Event, Timer
import time
import unittest
from unittest.mock import patch

from app.audio.config import AudioSettings
from app.audio.capture import Capture, DeviceUnavailable
from app.audio.model import verify_model
from app.audio.recognizer import Cancelled, Recognizer
from app.audio.service import AudioService
from app.audio.vad import Segmenter
from app.core.config import Settings, SettingsStore, ConfigError
from app.core.process_job import ProcessJob

SPEECH = struct.pack("<h", 2000) * 320  # Constant synthetic PCM, NOT speech.
SILENCE = bytes(640)


def wait_until(predicate, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError("Timed out waiting for audio state")


class VadTests(unittest.TestCase):
    def segmenter(self, **kwargs):
        return Segmenter(replace(AudioSettings(), **kwargs), lambda pcm, _rate: pcm == SPEECH)

    def test_silence_short_noise_and_minimum_speech(self):
        vad = self.segmenter()
        for pcm in [SILENCE] * 100 + [SPEECH] * 2 + [SILENCE] * 100 + [SPEECH] * 5 + [SILENCE] * 50:
            self.assertIsNone(vad.feed(pcm))
        self.assertFalse(vad.active)
        self.assertLessEqual(len(vad.preroll), 15)

    def test_endpoints_consecutive_utterances_no_duplicate(self):
        vad = self.segmenter()
        segments = []
        for _ in range(3):
            for pcm in [SPEECH] * 25 + [SILENCE] * 100:
                segment = vad.feed(pcm)
                if segment:
                    segments.append(segment)
        self.assertEqual(len(segments), 3)
        self.assertTrue(all(len(pcm) <= 800000 for pcm in segments))

    def test_maximum_duration_requires_silence_before_retrigger(self):
        vad = self.segmenter(maximum_seconds=2)
        segments = [segment for _ in range(500) if (segment := vad.feed(SPEECH))]
        self.assertEqual(len(segments), 1)
        self.assertEqual(len(segments[0]), 64000)
        self.assertTrue(vad.cooldown)
        for _ in range(30):
            vad.feed(SILENCE)
        self.assertFalse(vad.cooldown)

    def test_bad_frame_and_energy_gate(self):
        vad = Segmenter(AudioSettings(), lambda *_: True)
        with self.assertRaises(ValueError):
            vad.feed(b"bad")
        for _ in range(100):
            self.assertIsNone(vad.feed(SILENCE))
        self.assertFalse(vad.active)


class FakeBackend:
    class CallbackAbort(Exception): pass
    class PortAudioError(Exception): pass
    def __init__(self):
        self.closed = self.aborted = 0
        self.active = False
    def query_hostapis(self): return [{"name": "Test host"}]
    def query_devices(self, device=None, kind=None):
        info = {"name": "Synthetic microphone", "hostapi": 0, "max_input_channels": 1, "default_samplerate": 16000}
        return info if kind else [info]
    def check_input_settings(self, **kwargs): pass
    def RawInputStream(self, **kwargs):
        self.callback = kwargs["callback"]
        return self
    def start(self): self.active = True
    def abort(self):
        self.active = False
        self.aborted += 1
    def close(self): self.closed += 1


class CaptureTests(unittest.TestCase):
    def test_capture_off_aborts_releases_and_clears_queue(self):
        backend, cancel = FakeBackend(), Event()
        capture = Capture(AudioSettings(), cancel, backend)
        backend.callback(SPEECH, 320, None, False)
        self.assertEqual(capture.read(), [SPEECH])
        backend.callback(SPEECH, 320, None, False)
        cancel.set()
        with self.assertRaises(backend.CallbackAbort):
            backend.callback(SPEECH, 320, None, False)
        capture.close()
        capture.close()
        self.assertEqual((backend.aborted, backend.closed), (1, 1))
        self.assertTrue(capture.queue.empty())

    def test_input_selection_missing_and_disconnect(self):
        backend = FakeBackend()
        with self.assertRaises(DeviceUnavailable):
            Capture(replace(AudioSettings(), device="Missing"), Event(), backend)
        capture = Capture(replace(AudioSettings(), device="Test host | Synthetic microphone"), Event(), backend)
        backend.active = False
        with self.assertRaises(DeviceUnavailable): capture.read()
        capture.close()

    def test_queue_overflow_discards_stale_pcm(self):
        backend = FakeBackend()
        capture = Capture(AudioSettings(), Event(), backend)
        for _ in range(1000): backend.callback(SPEECH, 320, None, False)
        self.assertEqual(capture.queue.qsize(), 50)
        with self.assertRaises(BufferError): capture.read()
        self.assertTrue(capture.queue.empty())
        capture.close()


class ServiceTests(unittest.TestCase):
    def test_pending_next_turn_does_not_reuse_previous_latency(self):
        entered = Event()
        calls = []
        def recognize(pcm, settings, cancel):
            calls.append(1)
            if len(calls) == 2:
                entered.set()
                cancel.wait(2)
            return {"text": "synthetic timing fixture", "latency_seconds": .01}
        service = self.make_service(recognize)
        settings = replace(AudioSettings(), consent=True)
        service.configure(True, settings)
        for pcm in [SPEECH] * 20 + [SILENCE] * 30: self.queue.put(pcm)
        wait_until(lambda: service.snapshot()["latency_seconds"] == .01)
        for pcm in [SPEECH] * 20 + [SILENCE] * 30: self.queue.put(pcm)
        self.assertTrue(entered.wait(2))
        self.assertEqual(service.snapshot()["turn"], 2)
        self.assertIsNone(service.snapshot()["latency_seconds"])
        service.configure(False, settings)
        wait_until(lambda: service.snapshot()["status"] == "Microphone Disabled")

    def make_service(self, recognize=None, capture_failure=False):
        self.queue = Queue()
        self.opened = self.closed = 0
        owner = self
        class FakeCapture:
            def __init__(self, settings, cancel):
                if capture_failure: raise DeviceUnavailable("test unplug")
                owner.opened += 1
            def read(self):
                try: return [owner.queue.get(timeout=.01)]
                except Empty: return []
            def close(self): owner.closed += 1
        class FakeRecognizer:
            def transcribe(self, pcm, settings, cancel):
                if recognize: return recognize(pcm, settings, cancel)
                return {"text": "synthetic stub result", "latency_seconds": .01}
        service = AudioService(FakeCapture,
            lambda settings: Segmenter(settings, lambda pcm, rate: pcm == SPEECH),
            FakeRecognizer, preflight=lambda _: None)
        self.addCleanup(service.close)
        return service

    def test_requires_consent_and_repeated_on_off_cleans_up(self):
        service = self.make_service()
        with self.assertRaises(ValueError): service.configure(True, AudioSettings())
        settings = replace(AudioSettings(), consent=True)
        for _ in range(15):
            service.configure(True, settings)
            wait_until(lambda: service.snapshot()["status"] == "Listening")
            service.configure(False, settings)
            wait_until(lambda: service.snapshot()["status"] == "Microphone Disabled")
            self.assertEqual(self.opened, self.closed)
        self.assertEqual(self.opened, 15)

    def test_mute_cancels_recognition_and_discards_late_result(self):
        entered = Event()
        def recognize(pcm, settings, cancel):
            self.assertEqual(self.opened, self.closed)  # Device already released during recognition.
            entered.set()
            cancel.wait(2)
            return {"text": "late result must not appear", "latency_seconds": 1}
        service = self.make_service(recognize)
        settings = replace(AudioSettings(), consent=True)
        service.configure(True, settings)
        for pcm in [SPEECH] * 20 + [SILENCE] * 30: self.queue.put(pcm)
        self.assertTrue(entered.wait(2))
        service.configure(False, settings)
        wait_until(lambda: service.snapshot()["status"] == "Microphone Disabled")
        self.assertEqual(service.snapshot()["text"], "")
        self.assertFalse(service.snapshot()["capturing"])

    def test_close_during_unavailable_retry_is_prompt(self):
        service = self.make_service(capture_failure=True)
        service.configure(True, replace(AudioSettings(), consent=True))
        wait_until(lambda: service.snapshot()["status"] == "Device Unavailable")
        self.assertIn("test unplug", service.snapshot()["detail"])
        start = time.monotonic()
        service.close()
        self.assertLess(time.monotonic() - start, .5)
        self.assertFalse(service.thread.is_alive())

    def test_missing_dependency_or_model_error_does_not_open_device(self):
        service = self.make_service()
        def fail(_): raise ValueError("missing model")
        service.preflight = fail
        service.configure(True, replace(AudioSettings(), consent=True))
        wait_until(lambda: service.snapshot()["status"] == "Recognition Error")
        self.assertEqual(self.opened, 0)
        self.assertEqual(service.snapshot()["detail"], "missing model")

    def test_rapid_reconfiguration_latest_generation_wins(self):
        service = self.make_service()
        settings = replace(AudioSettings(), consent=True)
        for _ in range(100):
            service.configure(True, settings)
            service.configure(False, settings)
        wait_until(lambda: service.snapshot()["status"] == "Microphone Disabled")
        self.assertEqual(self.opened, self.closed)


class AudioConfigTests(unittest.TestCase):
    def test_model_hash_header_and_size_validation(self):
        # Artificial bytes validate only our file gate, never a real model load.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.bin"
            data = struct.pack("<iii", 0x67676D6C, 51865, 1500) + bytes(1_000_000)
            path.write_bytes(data)
            manifest = {"model": "tiny-q5_1", "license": "MIT", "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            metadata = path.with_suffix(".bin.json")
            metadata.write_text(json.dumps(manifest))
            self.assertEqual(verify_model(str(path)), path)
            path.write_bytes(data[:-1] + b"x")
            with self.assertRaisesRegex(ValueError, "SHA-256"): verify_model(str(path))
            path.write_bytes(struct.pack("<iii", 0x67676D6C, 51864, 1500) + bytes(1_000_000))
            with self.assertRaisesRegex(ValueError, "English-only"): verify_model(str(path))
            path.write_bytes(b"short")
            with self.assertRaisesRegex(ValueError, "size"): verify_model(str(path))

    def test_reference_scoring_and_normalization(self):
        from app.audio.evaluation import score
        self.assertEqual(score("Kamusta ka?", "kamusta ka")["wer"], 0)
        self.assertEqual(score("Can you help me sa project ko?", "Can you help sa project ko")["word_errors"], 1)
        self.assertEqual(score("ab", "ac")["cer"], .5)
        with self.assertRaises(ValueError): score("", "text")

    def test_upgrade_roundtrip_consent_and_invalid_audio(self):
        self.assertFalse(Settings.parse({}).audio.consent)
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory))
            settings = Settings(audio=replace(AudioSettings(), consent=True, auto_listen=True, language="tl"))
            store.save(settings)
            self.assertEqual(store.load().audio, settings.audio)
        for change in ({"consent": 1}, {"threads": 99}, {"maximum_seconds": 26}, {"sensitivity": float("nan")}, {"language": "en-only"}):
            with self.assertRaises(ConfigError): Settings.parse({"audio": change})

    def test_missing_model_and_english_only_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ggml-tiny.en.bin"
            with self.assertRaises(ValueError): verify_model(str(path))
            path.write_bytes(b"fake")
            with self.assertRaisesRegex(ValueError, "English-only"): verify_model(str(path))


class WorkerTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows crash cleanup")
    def test_owner_crash_closes_job_and_worker(self):
        import psutil
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "owned-worker.json"
            code = "\n".join([
                "import json,os,subprocess,sys,psutil",
                "from pathlib import Path",
                "from app.core.process_job import ProcessJob",
                "job=ProcessJob()",
                "child=subprocess.Popen([sys._base_executable,'-c','import sys,time; sys.stdin.buffer.read(1); time.sleep(30)'],stdin=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)",
                "job.assign(child)",
                "Path(sys.argv[1]).write_text(json.dumps({'pid':child.pid,'created':psutil.Process(child.pid).create_time()}))",
                "child.stdin.write(b'x'); child.stdin.flush()",
                "os._exit(73)",
            ])
            result = subprocess.run([sys.executable, "-c", code, str(marker)], timeout=5,
                                    creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
            self.assertEqual(result.returncode, 73, result.stderr)
            identity = json.loads(marker.read_text())
            def gone():
                try:
                    return psutil.Process(identity["pid"]).create_time() != identity["created"]
                except psutil.NoSuchProcess:
                    return True
            try:
                wait_until(gone, 3)
            finally:
                if not gone():
                    # Exact test-created PID AND creation identity, never name-based cleanup.
                    psutil.Process(identity["pid"]).terminate()

    def test_cancel_unresponsive_worker_even_when_pipe_write_is_blocked(self):
        real_popen = subprocess.Popen
        owned = []
        def stalled(_command, **kwargs):
            child = real_popen([getattr(sys, "_base_executable", sys.executable), "-c", "import time; time.sleep(30)"], **kwargs)
            owned.append(child)
            return child
        cancel = Event()
        timer = Timer(.2, cancel.set)
        timer.start()
        start = time.monotonic()
        try:
            with patch("app.audio.recognizer.subprocess.Popen", side_effect=stalled):
                with self.assertRaises(Cancelled):
                    Recognizer().transcribe(bytes(800000), AudioSettings(), cancel)
        finally:
            timer.cancel()
        self.assertLess(time.monotonic() - start, 2)
        self.assertIsNotNone(owned[0].poll())

    def test_worker_real_process_missing_model_clean_exit(self):
        recognizer = Recognizer()
        with self.assertRaisesRegex(RuntimeError, "Missing multilingual model"):
            recognizer.transcribe(SPEECH * 10, replace(AudioSettings(), model_path="missing-model.bin"), Event())
        self.assertIsNone(recognizer.process)

    def test_cancelled_or_oversized_request_does_not_spawn(self):
        recognizer, cancel = Recognizer(), Event()
        cancel.set()
        with self.assertRaises(Cancelled): recognizer.transcribe(SPEECH, AudioSettings(), cancel)
        cancel.clear()
        with self.assertRaises(ValueError): recognizer.transcribe(bytes(800002), AudioSettings(), cancel)
        self.assertIsNone(recognizer.process)

    @unittest.skipUnless(os.name == "nt", "Windows Job Object check")
    def test_job_close_terminates_only_owned_process(self):
        process = subprocess.Popen([getattr(sys, "_base_executable", sys.executable), "-c", "import sys,time; sys.stdin.buffer.read(1); time.sleep(30)"],
                                   stdin=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
        job = ProcessJob()
        try:
            job.assign(process)
            self.assertIn(process.pid, ProcessJob.owned_process_ids())
            process.stdin.write(b"x")
            process.stdin.flush()
            job.close()
            process.wait(timeout=5)
            self.assertIsNotNone(process.returncode)
            self.assertNotIn(process.pid, ProcessJob.owned_process_ids())
        finally:
            job.close()
            if process.poll() is None: process.kill()
            process.communicate(timeout=5)


if __name__ == "__main__": unittest.main()
