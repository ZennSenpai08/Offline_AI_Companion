from __future__ import annotations

from typing import Callable
import time
import math

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBitmap, QCloseEvent, QImage, QPainter, QRegion
from PySide6.QtWidgets import QApplication, QWidget

from app.avatar.renderer import CharacterRenderer
from app.avatar.animation_controller import AnimationController
from app.core.config import Settings
from app.core.geometry import Monitor, Rect, choose_monitor, clamp_position, fitted_size, remap_position


def current_monitors() -> list[Monitor]:
    app = QApplication.instance()
    screens = app.screens()
    primary = app.primaryScreen()
    screens.sort(key=lambda screen: screen != primary)
    return [Monitor(screen.name(), Rect(screen.availableGeometry().x(), screen.availableGeometry().y(), screen.availableGeometry().width(), screen.availableGeometry().height())) for screen in screens]


class Overlay(QWidget):
    settings_changed = Signal()
    context_requested = Signal(QPoint)
    exit_requested = Signal()
    warning = Signal(str)
    first_painted = Signal()
    frame_painted = Signal(float)

    def __init__(self, settings: Settings, renderer: CharacterRenderer):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if settings.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.settings = settings
        self.renderer = renderer
        self.click_through = False
        self.can_recover: Callable[[], bool] = lambda: False
        self._image = QImage()
        self._interaction_region = QRegion()
        self._drag_offset: QPoint | None = None
        self._ready = False
        self._first_paint = False
        self._connected_window_handle = None
        self._connected_screens = set()
        self.animation = AnimationController(self)
        self.setWindowTitle("Offline Companion — Animated placeholder")
        self.setAccessibleName("Original temporary companion character")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAutoFillBackground(False)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Temporary character • Drag to move • Right-click for controls")
        self._display_timer = QTimer(self)
        self._display_timer.setSingleShot(True)
        self._display_timer.setInterval(80)
        self._display_timer.timeout.connect(self._display_changed)
        app = QApplication.instance()
        app.screenAdded.connect(self._schedule_display_change)
        app.screenRemoved.connect(self._screen_removed)
        self._connect_screens()
        self.restore_placement()
        self._ready = True

    def _connect_screens(self) -> None:
        for screen in QApplication.instance().screens():
            if screen not in self._connected_screens:
                screen.availableGeometryChanged.connect(self._schedule_display_change)
                screen.geometryChanged.connect(self._schedule_display_change)
                screen.logicalDotsPerInchChanged.connect(self._schedule_display_change)
                self._connected_screens.add(screen)

    def _screen_removed(self, screen) -> None:
        self._connected_screens.discard(screen)
        self._schedule_display_change()

    def _schedule_display_change(self, *_args) -> None:
        self._display_timer.start()

    def _display_changed(self) -> None:
        self._connect_screens()
        if not current_monitors():
            return  # Wait for a display-added notification; do not spin.
        self._drag_offset = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.restore_placement()
        self.settings_changed.emit()

    def restore_placement(self, reset: bool = False) -> None:
        monitors = current_monitors()
        if not monitors:
            raise RuntimeError("No display is available for the companion.")
        base = (self.renderer.base_size.width(), self.renderer.base_size.height())
        saved = self.settings
        if reset or saved.x is None:
            monitor = monitors[0]
            size = fitted_size(base, saved.scale, monitor.area)
            x = monitor.area.x + monitor.area.width - size[0] - 32
            y = monitor.area.y + monitor.area.height - size[1] - 24
        else:
            probe = Rect(saved.x, saved.y, round(base[0] * saved.scale), round(base[1] * saved.scale))
            monitor = choose_monitor(probe, monitors, saved.screen_name)
            size = fitted_size(base, saved.scale, monitor.area)
            x, y = saved.x, saved.y
            if saved.work_area and saved.screen_name == monitor.name:
                x, y = remap_position(x, y, size, Rect(*saved.work_area), monitor.area)
        x, y = clamp_position(x, y, size, monitor.area)
        self.setFixedSize(*size)
        self.move(x, y)
        self._rebuild_image()
        self.record_placement()

    def _rebuild_image(self) -> None:
        if self.width() <= 0 or self.height() <= 0:
            return
        self._image = self.renderer.render(self.size(), self.devicePixelRatioF(), self.settings.flipped)
        logical = self._image.scaled(self.size(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        logical.setDevicePixelRatio(1.0)
        bitmap = QBitmap.fromImage(logical.createAlphaMask(Qt.ImageConversionFlag.ThresholdDither))
        self._interaction_region = QRegion(bitmap)
        # Cache a small motion envelope on scale/DPI changes, not on every frame.
        # Current-pose alpha is still used for press/context hit testing.
        radius = math.ceil(18 * min(self.width() / 240, self.height() / 360))
        horizontal = QRegion(self._interaction_region)
        for offset in range(-radius, radius + 1):
            horizontal |= self._interaction_region.translated(offset, 0)
        envelope = QRegion(horizontal)
        for offset in range(-radius, radius + 1):
            envelope |= horizontal.translated(0, offset)
        self.setMask(envelope)
        self.update()

    def hit_test(self, point: QPoint) -> bool:
        return not self.click_through and self.renderer.hit_test(point, self.size(), self.devicePixelRatioF(), self.settings.flipped, self.animation.motion.pose)

    def set_animation_preferences(self, *, enabled=None, fps=None, intensity=None, reduced_motion=None):
        values = vars(self.settings).copy()
        for name, value in (("animation_enabled", enabled), ("animation_fps", fps),
                            ("animation_intensity", intensity), ("reduced_motion", reduced_motion)):
            if value is not None:
                values[name] = value
        checked = Settings.parse(values)
        for name in ("animation_enabled", "animation_fps", "animation_intensity", "reduced_motion"):
            setattr(self.settings, name, getattr(checked, name))
        self.animation.configure()
        self.settings_changed.emit()

    def record_placement(self) -> None:
        monitors = current_monitors()
        if not monitors:
            return
        monitor = choose_monitor(Rect(self.x(), self.y(), self.width(), self.height()), monitors)
        self.settings.x, self.settings.y = self.x(), self.y()
        self.settings.screen_name = monitor.name
        area = monitor.area
        self.settings.work_area = [area.x, area.y, area.width, area.height]

    def settle_position(self) -> None:
        monitors = current_monitors()
        if not monitors:
            return
        monitor = choose_monitor(Rect(self.x(), self.y(), self.width(), self.height()), monitors)
        base = (self.renderer.base_size.width(), self.renderer.base_size.height())
        self.setFixedSize(*fitted_size(base, self.settings.scale, monitor.area))
        self.move(*clamp_position(self.x(), self.y(), (self.width(), self.height()), monitor.area))
        self._rebuild_image()
        self.record_placement()
        self.settings_changed.emit()

    def set_character_scale(self, scale: float) -> None:
        if not 0.5 <= scale <= 2.0:
            raise ValueError("Scale must be between 0.5 and 2.0.")
        center_x, bottom = self.x() + self.width() / 2, self.y() + self.height()
        monitors = current_monitors()
        if not monitors:
            return
        monitor = choose_monitor(Rect(self.x(), self.y(), self.width(), self.height()), monitors)
        self.settings.scale = scale
        size = fitted_size((self.renderer.base_size.width(), self.renderer.base_size.height()), scale, monitor.area)
        self.setFixedSize(*size)
        self.move(*clamp_position(round(center_x - size[0] / 2), bottom - size[1], size, monitor.area))
        self._rebuild_image()
        self.record_placement()
        self.settings_changed.emit()

    def set_flipped(self, enabled: bool) -> None:
        self.settings.flipped = bool(enabled)
        self._rebuild_image()
        self.settings_changed.emit()

    def set_always_on_top(self, enabled: bool) -> None:
        position = self.pos()
        self.settings.always_on_top = bool(enabled)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        self.show()
        self.move(position)
        self._rebuild_image()
        self.settings_changed.emit()

    def set_click_through(self, enabled: bool) -> bool:
        if enabled and not self.can_recover():
            self.warning.emit("Click-through requires an available tray or recovery hotkey.")
            return False
        if self.click_through == enabled:
            return True
        position = self.pos()
        self._drag_offset = None
        self.click_through = enabled
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, enabled)
        self.show()
        self.move(position)
        self._rebuild_image()
        self.settings_changed.emit()
        return True

    def recover(self) -> None:
        self.set_click_through(False)
        self.restore_placement(reset=True)
        self.show()
        self.raise_()
        self.settings_changed.emit()

    def paintEvent(self, _event) -> None:
        started = time.perf_counter()
        painter = QPainter(self)
        self.renderer.paint(painter, self.size(), self.devicePixelRatioF(), self.settings.flipped, self.animation.motion.pose)
        painter.end()
        self.frame_painted.emit((time.perf_counter() - started) * 1000)
        if not self._first_paint:
            self._first_paint = True
            self.first_painted.emit()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        handle = self.windowHandle()
        if handle and handle is not self._connected_window_handle:
            handle.screenChanged.connect(self._screen_changed)
            self._connected_window_handle = handle
        self._rebuild_image()
        self.animation.start()

    def hideEvent(self, event) -> None:
        self.animation.stop()
        super().hideEvent(event)

    def _screen_changed(self, _screen) -> None:
        # Do not clamp mid-drag; logical geometry remains under the pointer.
        QTimer.singleShot(0, self._rebuild_image)

    def event(self, event) -> bool:
        result = super().event(event)
        if event.type() == QEvent.Type.DevicePixelRatioChange and getattr(self, "_ready", False):
            QTimer.singleShot(0, self._rebuild_image)
        return result

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.hit_test(event.position().toPoint()):
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.settle_position()
            event.accept()
        else:
            event.ignore()

    def contextMenuEvent(self, event) -> None:
        if self.hit_test(event.pos()):
            self.context_requested.emit(event.globalPos())
            event.accept()
        else:
            event.ignore()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.animation.close()
        self.exit_requested.emit()
        event.accept()
