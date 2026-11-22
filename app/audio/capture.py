"""PortAudio callbacks only copy into a bounded queue. Native work is off the UI."""
from queue import Empty, Full, Queue
import time


class DeviceUnavailable(RuntimeError):
    pass


def input_devices():
    import sounddevice as sd
    hosts = sd.query_hostapis()
    return [(index, f"{hosts[device['hostapi']]['name']} | {device['name']}")
            for index, device in enumerate(sd.query_devices()) if device["max_input_channels"] > 0]


class Capture:
    def __init__(self, settings, cancel, backend=None):
        if backend is None:
            import sounddevice as backend
        self.backend = backend
        self.cancel = cancel
        self.queue = Queue(maxsize=50)  # At most one second, including native-rate PCM.
        self.overruns = 0
        self.stream = None
        self.pending = bytearray()
        self.resampler = None
        self.last_frame = time.monotonic()
        device = None
        if settings.device:
            hosts = backend.query_hostapis()
            matches = [index for index, info in enumerate(backend.query_devices())
                       if info['max_input_channels'] > 0 and
                       f"{hosts[info['hostapi']]['name']} | {info['name']}" == settings.device]
            if len(matches) != 1:
                raise DeviceUnavailable("Selected input is missing or ambiguous. Select the microphone again.")
            device = matches[0]
        info = backend.query_devices(device, "input")
        self.rate = 16000
        try:
            backend.check_input_settings(device=device, channels=1, dtype="int16", samplerate=self.rate)
        except backend.PortAudioError:
            self.rate = round(info["default_samplerate"])
            if self.rate not in (32000, 44100, 48000):
                raise DeviceUnavailable("Input does not support 16/32/44.1/48 kHz mono capture.")
            backend.check_input_settings(device=device, channels=1, dtype="int16", samplerate=self.rate)
            import soxr
            self.resampler = soxr.ResampleStream(self.rate, 16000, 1, dtype="int16", quality="HQ")
        try:
            self.stream = backend.RawInputStream(device=device, samplerate=self.rate,
                channels=1, dtype="int16", blocksize=self.rate // 50, callback=self._callback)
            self.stream.start()
        except Exception:
            self.close()
            raise

    def _callback(self, data, frames, timing, status):
        if self.cancel.is_set():
            raise self.backend.CallbackAbort()
        if status or frames != self.rate // 50 or len(data) > 1920:
            self.overruns += 1
            return
        try:
            self.queue.put_nowait(bytes(data))
        except Full:
            self.overruns += 1

    def read(self):
        if self.overruns:
            self.clear()
            self.overruns = 0
            raise BufferError("Audio overrun: discarded the incomplete utterance. Please repeat it.")
        try:
            block = self.queue.get(timeout=.05)
        except Empty:
            if not self.stream.active or time.monotonic() - self.last_frame > 2:
                raise DeviceUnavailable("Microphone disconnected or stopped delivering audio.")
            return []
        self.last_frame = time.monotonic()
        if self.resampler is not None:
            import numpy as np
            block = self.resampler.resample_chunk(np.frombuffer(block, dtype="int16")).tobytes()
        self.pending.extend(block)
        frames = []
        while len(self.pending) >= 640:
            frames.append(bytes(self.pending[:640]))
            del self.pending[:640]
        return frames

    def clear(self):
        while True:
            try:
                self.queue.get_nowait()
            except Empty:
                break
        self.pending.clear()
        if self.resampler is not None:
            self.resampler.clear()

    def close(self):
        try:
            if self.stream is not None:
                try:
                    self.stream.abort()
                finally:
                    self.stream.close()
                    self.stream = None
        finally:
            self.clear()
