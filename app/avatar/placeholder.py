"""Original code-drawn temporary character. No external artwork is used."""
from __future__ import annotations

from dataclasses import dataclass
import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap, QTransform

from .renderer import RendererInfo
from .motion import Pose


@dataclass(frozen=True)
class Shape:
    path: QPainterPath
    fill: str
    stroke: str = "#293945"
    width: float = 2.2


@dataclass(frozen=True)
class Layer:
    name: str
    pivot: tuple[float, float]
    parent: str | None
    shapes: tuple[Shape, ...]


def curve(commands: list[tuple]) -> QPainterPath:
    path = QPainterPath()
    for command, *points in commands:
        if command == "M": path.moveTo(*points)
        elif command == "L": path.lineTo(*points)
        elif command == "C": path.cubicTo(*points)
        elif command == "Q": path.quadTo(*points)
        elif command == "Z": path.closeSubpath()
        else: raise ValueError(f"Unknown path command: {command}")
    return path


def ellipse(x: float, y: float, width: float, height: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QRectF(x, y, width, height))
    return path


def rounded(x: float, y: float, width: float, height: float, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(QRectF(x, y, width, height), radius, radius)
    return path


class PlaceholderRenderer:
    """Original rig with cached raster layers and bounded hierarchical idle motion."""

    base_size = QSize(240, 360)

    def __init__(self) -> None:
        skin, hair, light, coat = "#ffdfca", "#386c78", "#69a6aa", "#f2e8d7"
        self.layers = (
            Layer("hair_back", (120, 75), "head", (
                Shape(curve([("M", 58, 105), ("C", 33, 164, 40, 210, 27, 241), ("Q", 61, 239, 74, 204), ("L", 166, 204), ("Q", 185, 239, 215, 241), ("C", 198, 203, 207, 151, 184, 105), ("Z",)]), hair),
            )),
            Layer("leg_left", (99, 288), None, (Shape(rounded(83, 278, 32, 62, 12), "#404959"),)),
            Layer("leg_right", (142, 288), None, (Shape(rounded(126, 278, 32, 62, 12), "#404959"),)),
            Layer("boot_left", (100, 329), "leg_left", (Shape(rounded(70, 322, 47, 27, 9), "#465e69"), Shape(rounded(73, 340, 42, 7, 3), "#a6c9bc", width=0))),
            Layer("boot_right", (141, 329), "leg_right", (Shape(rounded(124, 322, 47, 27, 9), "#465e69"), Shape(rounded(126, 340, 42, 7, 3), "#a6c9bc", width=0))),
            Layer("arm_left", (79, 204), "torso", (
                Shape(curve([("M", 80, 194), ("Q", 53, 201, 48, 244), ("L", 69, 252), ("L", 94, 212), ("Z",)]), coat),
            )),
            Layer("hand_left", (58, 250), "arm_left", (Shape(ellipse(44, 240, 26, 32), skin),)),
            Layer("arm_right", (162, 204), "torso", (
                Shape(curve([("M", 160, 194), ("Q", 187, 201, 193, 244), ("L", 171, 252), ("L", 147, 212), ("Z",)]), coat),
            )),
            Layer("hand_right", (181, 250), "arm_right", (Shape(ellipse(171, 240, 26, 32), skin),)),
            Layer("torso", (120, 286), None, (
                Shape(curve([("M", 83, 188), ("Q", 120, 174, 157, 188), ("L", 172, 286), ("Q", 121, 305, 68, 286), ("Z",)]), coat),
                Shape(curve([("M", 104, 211), ("L", 104, 286), ("L", 136, 286), ("L", 136, 211), ("Z",)]), "#b9cbd0", width=0),
                Shape(rounded(79, 252, 20, 18, 3), "#c9bca7", width=0),
                Shape(rounded(143, 252, 20, 18, 3), "#c9bca7", width=0),
                Shape(ellipse(116, 231, 8, 8), "#6a7b80", width=0),
                Shape(ellipse(116, 252, 8, 8), "#6a7b80", width=0),
            )),
            Layer("scarf", (120, 187), "torso", (
                Shape(curve([("M", 143, 191), ("Q", 171, 207, 166, 242), ("L", 143, 237), ("L", 126, 198), ("Z",)]), "#a8a2c9"),
                Shape(rounded(80, 174, 79, 34, 13), "#c7bfdf"),
            )),
            Layer("head", (120, 179), "torso", (
                Shape(ellipse(53, 49, 136, 139), skin),
                Shape(ellipse(48, 119, 19, 29), skin), Shape(ellipse(175, 119, 19, 29), skin),
            )),
            Layer("hair_front", (120, 75), "head", (
                Shape(curve([("M", 54, 133), ("C", 34, 100, 45, 32, 99, 23), ("Q", 132, 8, 168, 35), ("C", 207, 56, 201, 103, 184, 140), ("L", 176, 92), ("Q", 159, 89, 144, 65), ("Q", 127, 99, 93, 106), ("L", 103, 77), ("Q", 85, 109, 61, 115), ("Z",)]), hair),
                Shape(curve([("M", 64, 65), ("Q", 91, 28, 121, 35), ("Q", 89, 49, 77, 76), ("Z",)]), light, width=0),
            )),
            Layer("eye_left", (88, 130), "head", (
                Shape(ellipse(76, 118, 22, 31), "#f8faf7"),
                Shape(ellipse(80, 122, 15, 24), "#447985", width=0),
                Shape(ellipse(83, 125, 9, 17), "#213c4e", width=0),
                Shape(ellipse(81, 123, 6, 7), "#ffffff", width=0),
            )),
            Layer("eye_right", (152, 130), "head", (
                Shape(ellipse(142, 118, 22, 31), "#f8faf7"),
                Shape(ellipse(146, 122, 15, 24), "#447985", width=0),
                Shape(ellipse(149, 125, 9, 17), "#213c4e", width=0),
                Shape(ellipse(147, 123, 6, 7), "#ffffff", width=0),
            )),
            Layer("brows", (120, 110), "head", (
                Shape(curve([("M", 76, 111), ("Q", 87, 107, 98, 112)]), "transparent"),
                Shape(curve([("M", 141, 112), ("Q", 152, 107, 164, 111)]), "transparent"),
            )),
            Layer("cheeks", (120, 151), "head", (
                Shape(ellipse(66, 147, 22, 9), "#efb7ad", width=0),
                Shape(ellipse(153, 147, 22, 9), "#efb7ad", width=0),
            )),
            Layer("mouth", (120, 162), "head", (
                Shape(curve([("M", 110, 159), ("Q", 120, 169, 130, 159)]), "transparent", "#9b6d65", 2.4),
            )),
            Layer("hair_pin", (168, 83), "hair_front", (
                Shape(curve([("M", 169, 70), ("L", 173, 81), ("L", 184, 85), ("L", 173, 89), ("L", 169, 100), ("L", 165, 89), ("L", 154, 85), ("L", 165, 81), ("Z",)]), "#f2d68d", width=1.4),
            )),
        )
        self.info = RendererInfo("Original temporary layered character", True, tuple(layer.name for layer in self.layers), frozenset({"static_layers", "mirror", "idle_motion", "blink"}))
        self.neutral = Pose()
        self._density = None
        self._cache = []
        self._draw_groups = []
        self._transforms = [QTransform() for _ in self.layers]
        self._bounds = []
        self._closed_eyes = []
        for x in (76, 142):
            self._closed_eyes.append(curve([('M', x, 134), ('Q', x + 11, 139, x + 22, 134)]))
        self._eyelid_pen = QPen(QColor('#293945'), 2.2)
        self._eyelid_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        for layer in self.layers:
            bounds = QRectF()
            for shape in layer.shapes:
                bounds = bounds.united(shape.path.boundingRect())
            self._bounds.append(bounds.adjusted(-3, -3, 3, 3))

    def _prepare(self, size, dpr):
        density = min(size.width() / 240, size.height() / 360) * dpr
        if self._density == density:
            return
        self._density = density
        self._draw_groups.clear()
        self._cache.clear()  # Keep only the current scale/DPI, not an unbounded atlas.
        for layer, bounds in zip(self.layers, self._bounds):
            image = QImage(max(1, math.ceil(bounds.width() * density)), max(1, math.ceil(bounds.height() * density)), QImage.Format.Format_ARGB32_Premultiplied)
            image.setDevicePixelRatio(density)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.translate(-bounds.x(), -bounds.y())
            for shape in layer.shapes:
                painter.setBrush(QColor(shape.fill))
                if shape.width:
                    pen = QPen(QColor(shape.stroke), shape.width)
                    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    painter.setPen(pen)
                else:
                    painter.setPen(Qt.PenStyle.NoPen)
                painter.drawPath(shape.path)
            painter.end()
            self._cache.append((QPointF(bounds.x(), bounds.y()), QPixmap.fromImage(image), image))
        # Contiguous layers sharing a transform can be composited once. Keep the
        # individual assets for hit tests and future gesture-specific rendering.
        for indices in ((0,), (1, 2, 3, 4), (5, 6, 7, 8, 9, 10), (11,), (12,),
                        (13,), (14,), (15, 16, 17), (18,)):
            index = indices[0]
            if len(indices) == 1:
                position, pixmap, _ = self._cache[index]
            else:
                bounds = QRectF(self._bounds[index])
                for other in indices[1:]:
                    bounds = bounds.united(self._bounds[other])
                image = QImage(math.ceil(bounds.width() * density), math.ceil(bounds.height() * density), QImage.Format.Format_ARGB32_Premultiplied)
                image.setDevicePixelRatio(density)
                image.fill(Qt.GlobalColor.transparent)
                painter = QPainter(image)
                painter.translate(-bounds.x(), -bounds.y())
                for other in indices:
                    painter.drawPixmap(self._cache[other][0], self._cache[other][1])
                painter.end()
                position, pixmap = QPointF(bounds.x(), bounds.y()), QPixmap.fromImage(image)
            self._draw_groups.append((index, self.layers[index].name, position, pixmap))

    def _update_transforms(self, pose):
        for layer, transform in zip(self.layers, self._transforms):
            transform.reset()
            name = layer.name
            if name.startswith(('leg_', 'boot_')):
                continue  # Feet remain planted; leg/coat overlap hides small hip shifts.
            transform.translate(120 + 2 * pose.weight, 286)
            transform.rotate(pose.sway + .35 * pose.weight)
            transform.scale(1 + .008 * pose.breath, 1 + .012 * pose.breath)
            transform.translate(-120, -286)
            if name not in ('torso', 'scarf', 'arm_left', 'arm_right', 'hand_left', 'hand_right'):
                transform.translate(120, 179)
                transform.rotate(pose.head)
                transform.translate(-120, -179)
            if name in ('hair_back', 'hair_front', 'hair_pin'):
                transform.translate(120, 75)
                transform.rotate(pose.hair * (1 if name == 'hair_back' else .25))
                transform.translate(-120, -75)

    def paint(self, painter, size, dpr, flipped=False, pose=None):
        pose = pose if pose is not None else self.neutral
        self._prepare(size, dpr)
        self._update_transforms(pose)
        factor = min(size.width() / 240, size.height() / 360)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate((size.width() - 240 * factor) / 2, (size.height() - 360 * factor) / 2)
        painter.scale(factor, factor)
        if flipped:
            painter.translate(240, 0)
            painter.scale(-1, 1)
        for index, name, position, pixmap in self._draw_groups:
            painter.save()
            painter.setWorldTransform(self._transforms[index], True)
            eye = name in ('eye_left', 'eye_right')
            if eye:
                painter.save()
                painter.translate(0, 134)
                painter.scale(1, max(.015, pose.eye_open))
                painter.translate(0, -134)
                painter.setOpacity(min(1, pose.eye_open / .15))
            painter.drawPixmap(position, pixmap)
            if eye:
                painter.restore()
                if pose.eye_open < .2:
                    painter.setOpacity(1 - pose.eye_open / .2)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(self._eyelid_pen)
                    painter.drawPath(self._closed_eyes[0 if name == 'eye_left' else 1])
            painter.restore()
        painter.restore()

    def hit_test(self, point, size, dpr, flipped, pose):
        """Exact current layer alpha on demand; no per-frame hit-mask allocation."""
        self._prepare(size, dpr)
        self._update_transforms(pose)
        factor = min(size.width() / 240, size.height() / 360)
        x = (point.x() - (size.width() - 240 * factor) / 2) / factor
        y = (point.y() - (size.height() - 360 * factor) / 2) / factor
        local = QPointF(240 - x if flipped else x, y)
        for transform, bounds, cached in zip(self._transforms, self._bounds, self._cache):
            inverse, valid = transform.inverted()
            if not valid:
                continue
            p = inverse.map(local)
            px, py = int((p.x() - bounds.x()) * self._density), int((p.y() - bounds.y()) * self._density)
            image = cached[2]
            if 0 <= px < image.width() and 0 <= py < image.height() and image.pixelColor(px, py).alpha() > 32:
                return True
        return False

    def render(self, size: QSize, dpr: float, flipped: bool = False, pose: Pose | None = None) -> QImage:
        image = QImage(max(1, round(size.width() * dpr)), max(1, round(size.height() * dpr)), QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(dpr)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        try:
            self.paint(painter, size, dpr, flipped, pose)
        finally:
            painter.end()
        return image

    def close(self) -> None:
        self._draw_groups.clear()
        self._cache.clear()
        self.layers = ()
