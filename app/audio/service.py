"""Single background coordinator, latest-state mailbox and priority cancellation."""
from dataclasses import replace
import importlib.util
import logging
from threading import Event, Lock, Thread
import time

from .capture import Capture, DeviceUnavailable, input_devices
from .config import AudioSettings
from .model import verify_model
from .recognizer import Cancelled, Recognizer
from .vad import Segmenter

LOG = logging.getLogger(__name__)
DISABLED = "Microphone Disabled"


class AudioService:
    def __init__(self, capture_factory=Capture, segmenter_factory=Segmenter,
                 recognizer_factory=Recognizer, preflight=None):
        self.capture_factory = capture_factory
        self.segmenter_factory = segmenter_factory
        self.recognizer_factory = recognizer_factory
        self.preflight = preflight or self._preflight
        self.lock = Lock()
        self.wake = Event()
        self.cancel = Event()
        self.thread = None
        self.closed = False
        self.enabled = False
        self.generation = 0
        self.settings = AudioSettings()
        self.state = {"status": DISABLED, "detail": "", "text": "", "revision": 0,
                      "generation": 0, "turn": 0, "capturing": False, "latency_seconds": None}

    @staticmethod
    def _preflight(settings):
        missing = [name for name in ("sounddevice", "webrtcvad", "numpy", "soxr", "pywhispercpp")
                   if importlib.util.find_spec(name) is None]
        if missing:
            raise ValueError("Missing audio packages: " + ", ".join(missing) + ". Install requirements-audio.txt in the project venv.")
        verify_model(settings.model_path)

    def snapshot(self):
        with self.lock:
            return self.state.copy()

    def _publish(self, generation, **values):
        with self.lock:
            if generation != self.generation:
                return
            self.state.update(values)
            self.state["revision"] += 1

    def configure(self, enabled, settings):
        checked = AudioSettings.parse(settings)
        if enabled and not checked.consent:
            raise ValueError("Explicit microphone consent is required.")
        with self.lock:
            if self.closed:
                return
            self.cancel.set()
            self.cancel = Event()
            self.generation += 1
            self.enabled = bool(enabled)
            self.settings = replace(checked)
            self.state.update(generation=self.generation, text="", detail="", latency_seconds=None,
                              status="Starting microphone…" if enabled else "Stopping microphone…")
            self.state["revision"] += 1
            if self.thread is None:
                self.thread = Thread(target=self._run, name="companion-audio", daemon=True)
                self.thread.start()
        self.wake.set()

    def _run(self):
        while True:
            self.wake.wait()
            self.wake.clear()
            with self.lock:
                if self.closed:
                    return
                generation, settings, cancel, enabled = self.generation, self.settings, self.cancel, self.enabled
            if not enabled:
                self._publish(generation, status=DISABLED, capturing=False)
                continue
            try:
                self.preflight(settings)
                self._session(generation, settings, cancel)
            except Cancelled:
                pass
            except Exception as exc:
                LOG.warning("Audio session failed (%s)", type(exc).__name__)
                self._publish(generation, status="Recognition Error", detail=str(exc)[:1000], capturing=False)

    def _session(self, generation, settings, cancel):
        segmenter = self.segmenter_factory(settings)
        recognizer = self.recognizer_factory()
        retries = 0
        cooldown = False
        while not cancel.is_set():
            capture = None
            pcm = None
            try:
                try:
                    capture = self.capture_factory(settings, cancel)
                except Exception as exc:
                    raise DeviceUnavailable(f"Cannot open microphone: {type(exc).__name__}: {str(exc)[:500]}. Check device selection and Windows Settings → Privacy & security → Microphone → desktop apps.") from exc
                self._publish(generation, status="Listening", detail="", capturing=True)
                if cooldown:
                    # After a duration limit, wait for a real silence endpoint before another turn.
                    segmenter.cooldown = True
                while not cancel.is_set() and pcm is None:
                    try:
                        frames = capture.read()
                    except BufferError as exc:
                        segmenter.reset()
                        self._publish(generation, status="Listening", detail=str(exc))
                        continue
                    if frames:
                        retries = 0
                    for frame in frames:
                        was_active = segmenter.active
                        pcm = segmenter.feed(frame)
                        if segmenter.active != was_active:
                            self._publish(generation, status="Speech Detected" if segmenter.active else "Listening", detail="")
                        if pcm is not None:
                            break
                cooldown = segmenter.limited
            except DeviceUnavailable as exc:
                if capture is not None:
                    capture.close()
                    capture = None
                retries += 1
                self._publish(generation, status="Device Unavailable", detail=f"{exc} Retrying in 3 seconds ({retries}/5).", capturing=False)
                if retries >= 5:
                    self._publish(generation, detail=f"{exc} Toggle the microphone to retry; restart if a newly connected device is not listed.")
                    return
                cancel.wait(3)
            finally:
                if capture is not None:
                    capture.close()
                segmenter.reset()
            if cancel.is_set():
                raise Cancelled()
            if pcm is None:
                continue
            self._publish(generation, status="Transcribing", capturing=False,
                          detail="Maximum segment duration reached." if cooldown else "")
            with self.lock:
                turn = self.state["turn"] + 1
            self._publish(generation, turn=turn, latency_seconds=None)
            try:
                result = recognizer.transcribe(pcm, settings, cancel)
                self._publish(generation, text=result["text"], latency_seconds=result["latency_seconds"])
            finally:
                pcm = None
            cancel.wait(.3)  # Bounded settling interval; microphone remains closed.

    def close(self):
        with self.lock:
            self.closed = True
            self.cancel.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=6)
            if self.thread.is_alive():
                raise RuntimeError("Audio shutdown did not finish within six seconds.")
        with self.lock:
            self.state.update(status=DISABLED, text="", capturing=False)
            self.state["revision"] += 1
