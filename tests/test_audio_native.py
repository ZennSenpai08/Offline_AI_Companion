"""Installed native-library checks. Synthetic PCM is NOT a microphone/quality test."""
import importlib.util
from pathlib import Path
import random
import struct
from threading import Event
import unittest

from app.audio.capture import Capture
from app.audio.config import AudioSettings
from app.audio.model import DEFAULT_MODEL
from app.audio.recognizer import Recognizer
from app.audio.vad import Segmenter

LIBRARIES = all(importlib.util.find_spec(name) for name in ("webrtcvad", "numpy", "soxr", "pywhispercpp"))


@unittest.skipUnless(LIBRARIES, "Native Phase 4 packages unavailable; native checks NOT VERIFIED")
class NativeAudioTests(unittest.TestCase):
    def test_actual_webrtc_silence_low_noise_and_short_impulse(self):
        randomizer = random.Random(42)
        silence = bytes(640)
        noise = struct.pack("<320h", *(randomizer.randint(-20, 20) for _ in range(320)))
        impulse = struct.pack("<320h", *(randomizer.randint(-6000, 6000) for _ in range(320)))
        segmenter = Segmenter(AudioSettings())
        for frame in [silence] * 200 + [noise] * 200 + [impulse] + [silence] * 100:
            self.assertIsNone(segmenter.feed(frame))
        self.assertFalse(segmenter.active)
        self.assertLessEqual(len(segmenter.preroll), 15)

    def test_actual_soxr_native_rate_fallback_keeps_exact_vad_frames(self):
        for rate in (44100, 48000):
            class Backend:
                class PortAudioError(Exception): pass
                class CallbackAbort(Exception): pass
                active = True
                def query_devices(self, *args): return {"default_samplerate": rate}
                def check_input_settings(self, **kwargs):
                    if kwargs["samplerate"] == 16000: raise self.PortAudioError("Fixture forces fallback")
                def RawInputStream(self, **kwargs): return self
                def start(self): pass
                def abort(self): pass
                def close(self): pass
            capture = Capture(AudioSettings(), Event(), Backend())
            try:
                count = 0
                for _ in range(100):
                    capture._callback(bytes(rate // 50 * 2), rate // 50, None, False)
                    frames = capture.read()
                    self.assertTrue(all(len(frame) == 640 for frame in frames))
                    count += len(frames)
                self.assertGreater(count, 90)  # Remaining samples are SoXR filter delay, not lost unbounded PCM.
                self.assertLessEqual(count, 100)
                self.assertLess(len(capture.pending), 640)
            finally:
                capture.close()

    @unittest.skipUnless(DEFAULT_MODEL.exists(), "Installed Tiny model unavailable; native inference NOT VERIFIED")
    def test_real_quantized_model_load_inference_and_worker_exit(self):
        recognizer = Recognizer()
        result = recognizer.transcribe(bytes(32000 * 3), AudioSettings(), Event())
        self.assertIsInstance(result["text"], str)
        self.assertGreater(result["inference_seconds"], 0)
        self.assertGreaterEqual(result["latency_seconds"], result["inference_seconds"])
        self.assertIsNone(recognizer.process)


if __name__ == "__main__": unittest.main()
