"""Bounded, deterministic idle simulation. No Qt, threads, or inference work."""
from dataclasses import dataclass
import math
import random


@dataclass(slots=True)
class Pose:
    breath: float = 0.0
    sway: float = 0.0
    head: float = 0.0
    hair: float = 0.0
    weight: float = 0.0
    eye_open: float = 1.0


class Spring:
    __slots__ = ('value', 'velocity', 'frequency', 'damping')

    def __init__(self, frequency=6.0, damping=1.0):
        self.value = self.velocity = 0.0
        self.frequency, self.damping = frequency, damping

    def step(self, target, dt):
        self.velocity += (self.frequency**2 * (target - self.value)
                          - 2 * self.damping * self.frequency * self.velocity) * dt
        self.value += self.velocity * dt


def smooth(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


class IdleMotion:
    """One writer owns all pose channels; future gesture blending belongs here.

    Fixed 1/120 s integration is driven by elapsed time, independent of render FPS.
    Resume gaps are capped at 250 ms; no unbounded catch-up loop or event queue.
    """
    STEP = 1 / 120

    def __init__(self, seed=None, intensity=1.0, reduced_motion=False, enabled=True):
        self.random = random.Random(seed)
        self.pose = Pose()
        self.time = self.accumulator = self.breath_phase = 0.0
        self.breath_period = self.random.uniform(3.6, 5.2)
        self.breath_amplitude = self.random.uniform(.85, 1.05)
        self.next_blink = self.random.uniform(2.4, 5.5)
        self.blink_elapsed = -1.0
        self.double_pending = False
        self.blinks = self.double_blinks = self.breath_cycles = self.weight_shifts = 0
        self.next_head = self.random.uniform(2, 5)
        self.head_target = self.weight_target = 0.0
        self.next_weight = self.random.uniform(9, 18)
        self.head = Spring(3.5)
        self.weight = Spring(2.3)
        self.hair = Spring(8, .55)
        self.strength = intensity if enabled else 0.0
        self.motion_scale = .15 if reduced_motion else 1.0
        self.configure(intensity, reduced_motion, enabled)

    def configure(self, intensity, reduced_motion, enabled):
        if not math.isfinite(intensity) or not 0 <= intensity <= 1.5:
            raise ValueError('Animation intensity must be finite and between 0 and 1.5')
        self.target_strength = float(intensity) if enabled else 0.0
        self.target_motion_scale = .15 if reduced_motion else 1.0

    @property
    def settled_off(self):
        return self.target_strength == 0 and self.strength < .001

    def advance(self, elapsed):
        if not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError('Elapsed animation time must be finite and nonnegative')
        self.accumulator += min(elapsed, .25)
        while self.accumulator + 1e-12 >= self.STEP:
            self._step(self.STEP)
            self.accumulator = max(0.0, self.accumulator - self.STEP)
        return self.pose

    def _step(self, dt):
        self.time += dt
        self.strength += (self.target_strength - self.strength) * (1 - math.exp(-6 * dt))
        self.motion_scale += (self.target_motion_scale - self.motion_scale) * (1 - math.exp(-5 * dt))
        self.breath_phase += dt / self.breath_period
        if self.breath_phase >= 1:
            self.breath_phase -= 1
            self.breath_period = self.random.uniform(3.6, 5.2)
            self.breath_amplitude = self.random.uniform(.85, 1.05)
            self.breath_cycles += 1
        if self.time >= self.next_head:
            self.head_target = self.random.uniform(-1.8, 1.8)
            self.next_head = self.time + self.random.uniform(3, 7)
        if self.time >= self.next_weight:
            if self.weight_target:
                self.weight_target = 0.0
                self.next_weight = self.time + self.random.uniform(9, 18)
            else:
                self.weight_target = self.random.choice((-1, 1)) * self.random.uniform(.5, 1)
                self.weight_shifts += 1
                self.next_weight = self.time + self.random.uniform(4, 7)
        self.head.step(self.head_target, dt)
        self.weight.step(self.weight_target, dt)
        sway = .65 * math.sin(self.time * .68) + .2 * math.sin(self.time * 1.13)
        sway_velocity = .65 * .68 * math.cos(self.time * .68) + .2 * 1.13 * math.cos(self.time * 1.13)
        self.hair.step(-.65 * self.head.velocity - .9 * sway_velocity, dt)
        if self.blink_elapsed < 0 and self.time >= self.next_blink:
            self.blink_elapsed = 0.0
            self.blinks += 1
        eye = 1.0
        if self.blink_elapsed >= 0:
            self.blink_elapsed += dt
            t = self.blink_elapsed
            if t < .09:
                eye = 1 - smooth(t / .09)
            elif t < .125:
                eye = 0.0
            elif t < .265:
                eye = smooth((t - .125) / .14)
            else:
                self.blink_elapsed = -1.0
                if not self.double_pending and self.random.random() < .16:
                    self.double_pending = True
                    self.double_blinks += 1
                    self.next_blink = self.time + self.random.uniform(.15, .24)
                else:
                    self.double_pending = False
                    self.next_blink = self.time + self.random.uniform(2.4, 6.5)
        gain = self.strength * self.motion_scale
        pose = self.pose  # Reuse one output object; consumers must not mutate it.
        pose.breath = (.5 - .5 * math.cos(math.tau * self.breath_phase)) * self.breath_amplitude * gain
        pose.sway = sway * gain
        pose.head = self.head.value * gain
        pose.hair = max(-2.5, min(2.5, self.hair.value)) * gain
        pose.weight = self.weight.value * gain
        pose.eye_open = 1 - (1 - eye) * min(1, self.strength)
        if self.settled_off:
            pose.breath = pose.sway = pose.head = pose.hair = pose.weight = 0.0
            pose.eye_open = 1.0
