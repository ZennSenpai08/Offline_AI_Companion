"""Bounded 16 kHz mono s16 segmentation; no Qt, files or recognition here."""
from collections import deque
from math import sqrt
from array import array

RATE = 16000
FRAME_MS = 20
FRAME_BYTES = 640


class Segmenter:
    def __init__(self, settings, detector=None):
        if detector is None:
            import webrtcvad
            detector = webrtcvad.Vad(settings.vad_mode).is_speech
        self.settings = settings
        self.detector = detector
        self.preroll = deque(maxlen=15)
        self.frames = []
        self.active = False
        self.voiced = self.silent = self.onset = 0
        self.limited = False
        self.cooldown = False
        self.noise_floor = 40.0

    def reset(self):
        self.preroll.clear()
        self.frames.clear()
        self.active = False
        self.voiced = self.silent = self.onset = 0
        self.cooldown = False

    def feed(self, frame: bytes) -> bytes | None:
        if len(frame) != FRAME_BYTES:
            raise ValueError("VAD requires exactly 20 ms of 16 kHz mono s16 PCM.")
        samples = array("h", frame)
        energy = sqrt(sum(sample * sample for sample in samples) / len(samples))
        detected = self.detector(frame, RATE)
        # Adaptive floor only follows non-speech, with a bounded sensitivity gate.
        if not detected:
            self.noise_floor += .02 * (min(energy, 1200) - self.noise_floor)
        voiced = detected and energy >= max(80, self.noise_floor * 1.8) / self.settings.sensitivity
        if self.cooldown:
            self.silent = 0 if voiced else self.silent + FRAME_MS
            if self.silent >= self.settings.silence_ms:
                self.reset()
            return None
        if not self.active:
            self.preroll.append(frame)
            self.onset = self.onset + FRAME_MS if voiced else 0
            if self.onset >= 60:
                self.active = True
                self.voiced = self.onset
                self.frames.extend(self.preroll)
                self.preroll.clear()
            return None
        self.frames.append(frame)
        self.voiced += FRAME_MS if voiced else 0
        self.silent = 0 if voiced else self.silent + FRAME_MS
        limit = len(self.frames) >= self.settings.maximum_seconds * 1000 // FRAME_MS
        if limit or self.silent >= self.settings.silence_ms:
            result = b"".join(self.frames) if self.voiced >= self.settings.minimum_ms else None
            self.reset()
            self.limited = limit
            self.cooldown = limit  # Require an endpoint before recognizing another maximum-length turn.
            return result
        return None
