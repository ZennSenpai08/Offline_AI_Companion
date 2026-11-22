from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    def intersection_area(self, other: Rect) -> int:
        width = max(0, min(self.x + self.width, other.x + other.width) - max(self.x, other.x))
        height = max(0, min(self.y + self.height, other.y + other.height) - max(self.y, other.y))
        return width * height


@dataclass(frozen=True)
class Monitor:
    name: str
    area: Rect


def choose_monitor(rect: Rect, monitors: list[Monitor], preferred: str = "") -> Monitor:
    if not monitors:
        raise ValueError("No display is currently available.")
    if preferred:
        for monitor in monitors:
            if monitor.name == preferred:
                return monitor
    # Prefer overlap, then the closest work area; handles negative origins and gaps.
    def rank(monitor: Monitor) -> tuple[int, float]:
        area = monitor.area
        cx, cy = rect.x + rect.width / 2, rect.y + rect.height / 2
        dx = max(area.x - cx, 0, cx - (area.x + area.width))
        dy = max(area.y - cy, 0, cy - (area.y + area.height))
        return rect.intersection_area(area), -(dx * dx + dy * dy)
    return max(monitors, key=rank)


def fitted_size(base: tuple[int, int], scale: float, area: Rect) -> tuple[int, int]:
    if min(*base, area.width, area.height) <= 0 or scale <= 0:
        raise ValueError("Positive dimensions and scale are required.")
    factor = min(scale, area.width / base[0], area.height / base[1])
    return max(1, round(base[0] * factor)), max(1, round(base[1] * factor))


def clamp_position(x: int, y: int, size: tuple[int, int], area: Rect) -> tuple[int, int]:
    return (
        max(area.x, min(x, area.x + max(0, area.width - size[0]))),
        max(area.y, min(y, area.y + max(0, area.height - size[1]))),
    )


def remap_position(x: int, y: int, size: tuple[int, int], old: Rect, new: Rect) -> tuple[int, int]:
    # Preserve the relative location when resolution, taskbar or monitor origin changes.
    fx = max(0.0, min(1.0, (x - old.x) / max(1, old.width - size[0])))
    fy = max(0.0, min(1.0, (y - old.y) / max(1, old.height - size[1])))
    return clamp_position(round(new.x + fx * max(0, new.width - size[0])), round(new.y + fy * max(0, new.height - size[1])), size, new)
