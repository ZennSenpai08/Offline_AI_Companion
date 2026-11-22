from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage
from .motion import Pose


@dataclass(frozen=True)
class RendererInfo:
    name: str
    placeholder: bool
    layers: tuple[str, ...]
    capabilities: frozenset[str]


class CharacterRenderer(Protocol):
    """UI owns this renderer. AI code will only send pose/state events.

    A single animation compositor supplies the pose; renderers do not run clocks.
    Returned images use physical pixels with a Qt device-pixel-ratio tag.
    """

    base_size: QSize
    info: RendererInfo

    def render(self, size: QSize, dpr: float, flipped: bool = False, pose: Pose | None = None) -> QImage: ...

    def paint(self, painter, size: QSize, dpr: float, flipped: bool, pose: Pose) -> None: ...

    def hit_test(self, point, size: QSize, dpr: float, flipped: bool, pose: Pose) -> bool: ...

    def close(self) -> None: ...
