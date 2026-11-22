from __future__ import annotations

import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import time
from dataclasses import replace

from PySide6.QtCore import QObject, QStandardPaths, QTimer, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox

from app.avatar.placeholder import PlaceholderRenderer
from app.core.config import ConfigError, SettingsStore
from app.core.instance import InstanceLockError, SingleInstance
from app.desktop.hotkey import RecoveryHotkey
from app.desktop.overlay import Overlay
from app.desktop.tray import DesktopControls
from app.audio.service import AudioService
from app.desktop.microphone import MicrophonePanel, MicrophoneSettings

LOG = logging.getLogger(__name__)


class CompanionController(QObject):
    def __init__(self, app: QApplication, store: SettingsStore, reset_position: bool = False):
        super().__init__(app)
        self.app = app
        self.store = store
        self.settings = store.load()
        self.renderer = PlaceholderRenderer()
        self.overlay = Overlay(self.settings, self.renderer)
        self.icon = QIcon(QPixmap.fromImage(self.renderer.render(self.renderer.base_size, 1.0)))
        app.setWindowIcon(self.icon)
        self.overlay.setWindowIcon(self.icon)
        self.controls = DesktopControls(self.overlay, self.icon)
        self.audio = AudioService()
        self.microphone_enabled = False
        self.mic_panel = MicrophonePanel(self.overlay)
        self.mic_panel.toggle_requested.connect(lambda: self.set_microphone(not self.microphone_enabled))
        self.controls.microphone_requested.connect(self.set_microphone)
        self.controls.microphone_settings_requested.connect(self.audio_settings)
        self.audio_timer = QTimer(self)
        self.audio_timer.setInterval(100)
        self.audio_timer.timeout.connect(self.refresh_audio)
        self._audio_revision = -1
        self.hotkey = RecoveryHotkey(app, self.overlay.recover)
        self.overlay.can_recover = lambda: self.hotkey.registered or self.controls.available()
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(300)
        self.save_timer.timeout.connect(self.save)
        self.overlay.settings_changed.connect(self.save_timer.start)
        self.overlay.warning.connect(self.show_warning)
        self.overlay.exit_requested.connect(app.quit)
        self.controls.exit_requested.connect(app.quit)
        self._closed = False
        self._save_error_shown = False
        app.aboutToQuit.connect(self.close)
        if reset_position:
            self.overlay.restore_placement(reset=True)

    def start(self) -> None:
        self.controls.show()
        self.overlay.show()
        self.mic_panel.follow()
        self.audio_timer.start()
        if self.settings.audio.consent and self.settings.audio.auto_listen:
            self.set_microphone(True)
        self.save_timer.start()

    def set_microphone(self, enabled):
        if enabled and not self.settings.audio.consent:
            answer = QMessageBox.question(self.overlay, "Enable offline microphone?",
                "The companion will listen through your selected microphone and transcribe speech locally. "
                "Audio is not uploaded or saved. Capture pauses during transcription. "
                "You can disable and release the microphone with the visible button or tray. "
                "Windows must also allow desktop microphone access.\n\nEnable the microphone and remember this choice for future launches?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                self.controls.mic_action.setChecked(False)
                return
            self.settings.audio = replace(self.settings.audio, consent=True)
        self.microphone_enabled = bool(enabled)
        self.settings.audio = replace(self.settings.audio, auto_listen=bool(enabled))
        self.audio.configure(enabled, self.settings.audio)
        self.controls.mic_action.setChecked(bool(enabled))
        self.overlay.settings_changed.emit()
        self.refresh_audio()

    def audio_settings(self):
        dialog = MicrophoneSettings(self.settings.audio, self.overlay)
        if dialog.exec():
            self.settings.audio = dialog.value()
            if self.microphone_enabled:
                self.audio.configure(True, self.settings.audio)
            self._audio_revision = -1
            self.refresh_audio()
            self.overlay.settings_changed.emit()
        dialog.deleteLater()

    def refresh_audio(self):
        state = self.audio.snapshot()
        if state["revision"] != self._audio_revision:
            self._audio_revision = state["revision"]
            self.mic_panel.present(state, self.microphone_enabled, self.settings.audio.preview)
            self.controls.tray.setToolTip("Offline Companion • " + state["status"])

    def show_warning(self, text: str) -> None:
        LOG.warning(text)
        QMessageBox.warning(self.overlay, "Offline Companion", text)

    def save(self) -> None:
        try:
            self.overlay.record_placement()
            self.store.save(self.settings)
            self._save_error_shown = False
        except (OSError, ConfigError):
            LOG.exception("Cannot save window settings")
            if not self._closed and not self._save_error_shown:
                self._save_error_shown = True
                self.show_warning(f"Cannot save window settings to {self.store.path}. Check folder permissions. Your previous settings were preserved.")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.audio_timer.stop()
        try:
            self.audio.close()
        except RuntimeError:
            LOG.exception("Audio did not finish shutdown cleanly")
            self.app.exit(1)
        self.mic_panel.close()
        self.overlay.animation.close()
        self.save_timer.stop()
        self.overlay._display_timer.stop()
        self.save()
        self.hotkey.close()
        self.controls.close()
        self.overlay.hide()
        self.renderer.close()


def arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline Companion — Phase 4 offline microphone and speech recognition")
    parser.add_argument("--data-dir", type=Path, help="Override settings/log directory (useful for isolated tests)")
    parser.add_argument("--reset-position", action="store_true", help="Recover character onto the primary monitor")
    parser.add_argument("--benchmark-seconds", type=float, default=0, help="Opt-in 3–600 second instrumented run, then clean exit")
    parser.add_argument("--report", type=Path, help="JSON benchmark result path")
    parser.add_argument("--snapshot", type=Path, help="Save a character-only transparent PNG after first paint")
    parser.add_argument("--animation-fps", type=int, choices=(30, 60), help="Set and persist animation frame rate")
    result = parser.parse_args(argv)
    if result.benchmark_seconds != 0 and not 3 <= result.benchmark_seconds <= 600:
        parser.error("--benchmark-seconds must be between 3 and 600")
    if result.report and not result.benchmark_seconds:
        parser.error("--report requires --benchmark-seconds")
    return result


def main(argv: list[str] | None = None, started_at: float | None = None) -> int:
    options = arguments(argv)
    started_at = started_at if started_at is not None else time.perf_counter()
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication([sys.argv[0]])
    app.setApplicationName("OfflineCompanion")
    app.setOrganizationName("OfflineCompanion")
    app.setQuitOnLastWindowClosed(False)
    directory = options.data_dir or Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    directory = directory.resolve()
    try:
        # Hold ownership through startup, saves, all cleanup and error paths.
        with SingleInstance(directory):
            return run_owned_application(app, options, directory, started_at)
    except InstanceLockError as exc:
        print(f"{exc.title}\n{exc}", file=sys.stderr)
        dialog = QMessageBox.information if exc.kind == "active" else QMessageBox.critical
        dialog(None, exc.title, str(exc))
        return 3 if exc.kind in ("active", "unverified", "stale") else 2


def run_owned_application(app: QApplication, options: argparse.Namespace, directory: Path, started_at: float) -> int:
    try:
        log_handler = RotatingFileHandler(directory / "companion.log", maxBytes=256 * 1024, backupCount=2, encoding="utf-8")
    except OSError as exc:
        QMessageBox.critical(None, "Cannot create log file", str(exc))
        return 2
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=[log_handler, logging.StreamHandler()])
    controller = None
    probe = None
    status = 0
    original_exception_hook = sys.excepthook
    def on_unhandled(kind, value, traceback):
        nonlocal status
        status = 1
        LOG.critical("Unhandled application error", exc_info=(kind, value, traceback))
        QMessageBox.critical(None, "Offline Companion error", f"{value}\n\nSee {directory / 'companion.log'}")
        app.exit(1)
    sys.excepthook = on_unhandled
    try:
        controller = CompanionController(app, SettingsStore(directory), options.reset_position)
        if options.animation_fps is not None:
            controller.overlay.set_animation_preferences(fps=options.animation_fps)
        if options.benchmark_seconds:
            from app.performance.probe import DesktopProbe
            probe = DesktopProbe(started_at, options.benchmark_seconds, options.report or directory / "benchmark.json", controller)
            controller.overlay.first_painted.connect(probe.painted)
            controller.overlay.frame_painted.connect(probe.frame_painted)
            probe.start()
            QTimer.singleShot(round(options.benchmark_seconds * 1000), app.quit)
        if options.snapshot:
            def snapshot():
                nonlocal status
                try:
                    options.snapshot.parent.mkdir(parents=True, exist_ok=True)
                    overlay = controller.overlay
                    if not controller.renderer.render(overlay.size(), overlay.devicePixelRatioF(), overlay.settings.flipped, overlay.animation.motion.pose).save(str(options.snapshot)):
                        raise OSError("Qt could not write the character snapshot")
                except OSError:
                    LOG.exception("Snapshot failed")
                    status = 2
            controller.overlay.first_painted.connect(lambda: QTimer.singleShot(0, snapshot))
        controller.start()
        LOG.info("Phase 4 started: platform=%s, tray=%s, recovery_hotkey=%s, lock=%s", app.platformName(), controller.controls.available(), controller.hotkey.registered, directory / "application.lock")
        status = app.exec() or status
    except (ConfigError, OSError, RuntimeError) as exc:
        LOG.exception("Startup failed")
        QMessageBox.critical(None, "Offline Companion startup failed", str(exc))
        status = 2
    finally:
        if probe is not None:
            try:
                probe.finish()
                LOG.info("Benchmark written to %s", probe.output)
            except (OSError, ValueError):
                LOG.exception("Benchmark report failed")
                status = 2
        if controller is not None:
            controller.close()
        sys.excepthook = original_exception_hook
        logging.shutdown()
    return status
