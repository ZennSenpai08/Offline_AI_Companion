from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QActionGroup, QIcon
from PySide6.QtWidgets import QMenu, QMessageBox, QSystemTrayIcon

from .overlay import Overlay


class DesktopControls(QObject):
    exit_requested = Signal()
    microphone_requested = Signal(bool)
    microphone_settings_requested = Signal()

    def __init__(self, overlay: Overlay, icon: QIcon):
        super().__init__(overlay)
        self.overlay = overlay
        self.menu = QMenu(overlay)
        self.menu.addAction("Recover character / Disable click-through", overlay.recover)
        self.mic_action = self.menu.addAction("Microphone ON")
        self.mic_action.setCheckable(True)
        self.mic_action.triggered.connect(lambda checked=False: self.microphone_requested.emit(checked))
        self.menu.addAction("Microphone settings…", lambda: self.microphone_settings_requested.emit())
        self.top_action = self.menu.addAction("Always on top")
        self.top_action.setCheckable(True)
        self.top_action.triggered.connect(overlay.set_always_on_top)
        self.click_action = self.menu.addAction("Click-through")
        self.click_action.setCheckable(True)
        self.click_action.triggered.connect(self._toggle_click_through)
        self.flip_action = self.menu.addAction("Face other direction")
        self.flip_action.setCheckable(True)
        self.flip_action.triggered.connect(overlay.set_flipped)
        size_menu = self.menu.addMenu("Character size")
        self.size_group = QActionGroup(self)
        self.size_group.setExclusive(True)
        self.size_actions = []
        for scale in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
            action = size_menu.addAction(f"{round(scale * 100)}%")
            action.setCheckable(True)
            action.setData(scale)
            action.triggered.connect(lambda _checked=False, value=scale: overlay.set_character_scale(value))
            self.size_group.addAction(action)
            self.size_actions.append(action)
        motion_menu = self.menu.addMenu("Animation")
        self.animation_action = motion_menu.addAction("Enable animation")
        self.animation_action.setCheckable(True)
        self.animation_action.triggered.connect(lambda enabled: overlay.set_animation_preferences(enabled=enabled))
        self.reduced_action = motion_menu.addAction("Reduced motion")
        self.reduced_action.setCheckable(True)
        self.reduced_action.triggered.connect(lambda enabled: overlay.set_animation_preferences(reduced_motion=enabled))
        self.fps_group = QActionGroup(self)
        self.fps_group.setExclusive(True)
        self.fps_actions = []
        for fps in (30, 60):
            action = motion_menu.addAction(f"{fps} FPS")
            action.setCheckable(True)
            action.setData(fps)
            action.triggered.connect(lambda _checked=False, value=fps: overlay.set_animation_preferences(fps=value))
            self.fps_group.addAction(action)
            self.fps_actions.append(action)
        intensity_menu = motion_menu.addMenu("Motion intensity")
        self.intensity_group = QActionGroup(self)
        self.intensity_group.setExclusive(True)
        self.intensity_actions = []
        for label, value in (("Subtle", .5), ("Normal", 1.0), ("Expressive", 1.5)):
            action = intensity_menu.addAction(label)
            action.setCheckable(True)
            action.setData(value)
            action.triggered.connect(lambda _checked=False, amount=value: overlay.set_animation_preferences(intensity=amount))
            self.intensity_group.addAction(action)
            self.intensity_actions.append(action)
        self.menu.addSeparator()
        self.menu.addAction("About this temporary character", self.show_about)
        self.menu.addSeparator()
        self.exit_action = self.menu.addAction("Exit application", lambda _checked=False: self.exit_requested.emit())
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("Offline Companion • Microphone Disabled")
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._activated)
        self.menu.aboutToShow.connect(self.sync)
        overlay.settings_changed.connect(self.sync)
        overlay.context_requested.connect(self.menu.popup)
        self.sync()

    def show(self) -> None:
        self.tray.show()

    def available(self) -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable() and self.tray.isVisible()

    def _activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.overlay.recover()

    def _toggle_click_through(self, enabled: bool) -> None:
        self.overlay.set_click_through(enabled)
        self.sync()

    def sync(self) -> None:
        self.top_action.setChecked(self.overlay.settings.always_on_top)
        self.click_action.setChecked(self.overlay.click_through)
        self.flip_action.setChecked(self.overlay.settings.flipped)
        for action in self.size_actions:
            action.setChecked(action.data() == self.overlay.settings.scale)
        self.animation_action.setChecked(self.overlay.settings.animation_enabled)
        self.reduced_action.setChecked(self.overlay.settings.reduced_motion)
        for action in self.fps_actions:
            action.setChecked(action.data() == self.overlay.settings.animation_fps)
        for action in self.intensity_actions:
            action.setChecked(action.data() == self.overlay.settings.animation_intensity)

    def show_about(self) -> None:
        QMessageBox.information(self.overlay, "Offline Companion — Phase 4", "Original temporary layered character with procedural idle animation.\n\nMicrophone enablement requires explicit consent and installed offline speech components. Raw audio is not saved. Use the visible microphone button or tray to disable capture.\n\nRecovery: Ctrl+Alt+Shift+R (when available). Restart disables click-through.\n\nConversation and voice output are not implemented.")

    def close(self) -> None:
        self.menu.close()
        self.tray.hide()
