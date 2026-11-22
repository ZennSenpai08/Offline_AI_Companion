"""Qt scheduling only; no inference or blocking work belongs in this loop."""
import math
import time

from PySide6.QtCore import QObject, QTimer, Qt

from .motion import IdleMotion


class AnimationController(QObject):
    def __init__(self, overlay, seed=None):
        super().__init__(overlay)
        self.overlay = overlay
        s = overlay.settings
        self.motion = IdleMotion(seed, s.animation_intensity, s.reduced_motion, s.animation_enabled)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.tick)
        self.last = self.deadline = 0.0
        self.closed = False
        self.updates = 0
        self.period = 1 / s.animation_fps

    def configure(self):
        s = self.overlay.settings
        self.period = 1 / s.animation_fps
        self.motion.configure(s.animation_intensity, s.reduced_motion, s.animation_enabled)
        if self.overlay.isVisible():
            self.start()

    def start(self):
        if self.closed or self.motion.settled_off:
            return
        self.last = time.perf_counter()
        self.deadline = self.last + self.period
        self.timer.start(max(1, math.ceil(self.period * 1000)))

    def tick(self):
        if self.closed or not self.overlay.isVisible():
            self.stop()
            return
        now = time.perf_counter()
        self.motion.advance(now - self.last)
        self.last = now
        self.updates += 1
        self.overlay.update()
        if self.motion.settled_off:
            return
        self.deadline += self.period
        if self.deadline <= now:
            self.deadline += (math.floor((now - self.deadline) / self.period) + 1) * self.period
        self.timer.start(max(1, math.ceil((self.deadline - now) * 1000)))

    def stop(self):
        self.timer.stop()

    def close(self):
        self.closed = True
        self.stop()
