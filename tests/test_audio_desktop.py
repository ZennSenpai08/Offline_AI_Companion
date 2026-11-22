"""Qt integration with simulated devices/recognition, not hardware acceptance."""
from dataclasses import replace
from pathlib import Path
from threading import Event
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.audio.config import AudioSettings
from app.audio.service import AudioService
from app.core.config import Settings, SettingsStore
from app.main import CompanionController


class AudioDesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = SettingsStore(Path(self.directory.name))
        self.controller = CompanionController(self.app, self.store)

    def tearDown(self):
        self.controller.close()
        self.controller.overlay.deleteLater()
        self.controller.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.directory.cleanup()

    def test_no_capture_without_consent_and_decline_preserves_disabled(self):
        self.controller.settings.audio = AudioSettings(auto_listen=True)
        self.controller.start()
        QTest.qWait(50)
        self.assertIsNone(self.controller.audio.thread)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            self.controller.set_microphone(True)
        self.assertFalse(self.controller.settings.audio.consent)
        self.assertFalse(self.controller.microphone_enabled)
        self.assertIsNone(self.controller.audio.thread)

    def test_consent_error_indicator_and_tray_mute_release(self):
        def missing(_): raise ValueError("Synthetic missing model")
        self.controller.audio.preflight = missing
        self.controller.start()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.controller.set_microphone(True)
        QTest.qWait(150)
        self.assertTrue(self.controller.settings.audio.consent)
        self.assertTrue(self.controller.controls.mic_action.isChecked())
        self.assertEqual(self.controller.mic_panel.status.text(), "Recognition Error")
        self.controller.controls.mic_action.trigger()
        QTest.qWait(150)
        self.assertEqual(self.controller.mic_panel.status.text(), "Microphone Disabled")
        self.assertFalse(self.controller.settings.audio.auto_listen)

    def test_animation_and_controls_continue_during_background_recognition(self):
        entered, release = Event(), Event()
        class Capture:
            def __init__(self, settings, cancel): self.cancel = cancel
            def read(self): return [bytes(640)]
            def close(self): pass
        class Segmenter:
            active = False
            limited = False
            def __init__(self, settings): pass
            def feed(self, frame): return bytes(6400)
            def reset(self): pass
        class Recognizer:
            def transcribe(self, pcm, settings, cancel):
                entered.set()
                while not cancel.wait(.01) and not release.is_set(): pass
                return {"text": "Synthetic GUI fixture", "latency_seconds": .5}
        self.controller.audio = AudioService(Capture, Segmenter, Recognizer, preflight=lambda _: None)
        self.controller.settings.audio = AudioSettings(consent=True)
        self.controller.start()
        self.controller.set_microphone(True)
        QTest.qWait(150)
        self.assertTrue(entered.is_set())
        self.assertEqual(self.controller.audio.snapshot()["status"], "Transcribing")
        frames = []
        self.controller.overlay.frame_painted.connect(frames.append)
        QTest.qWait(400)
        self.assertGreater(len(frames), 5)
        self.controller.overlay.set_character_scale(.75)
        self.controller.overlay.set_always_on_top(False)
        self.controller.overlay.set_click_through(True)
        self.assertTrue(self.controller.mic_panel.toggle.isEnabled())
        self.controller.mic_panel.toggle.click()
        QTest.qWait(150)
        self.assertEqual(self.controller.audio.snapshot()["status"], "Microphone Disabled")
        self.assertEqual(self.controller.audio.snapshot()["text"], "")

    def test_preview_plain_text_bounded_following_and_expiry(self):
        self.controller.start()
        panel = self.controller.mic_panel
        state = {"status": "Listening", "detail": "", "text": "<b>not markup</b> " * 100}
        panel.present(state, True, True)
        self.assertEqual(len(panel.preview.text()), 400)
        self.assertGreaterEqual(panel.y(), self.controller.overlay.y())
        panel.clear_preview()
        panel.present(state, True, True)
        self.assertFalse(panel.preview.isVisible())
        panel.present(dict(state, text=""), False, True)
        self.assertEqual(panel.preview.text(), "")


if __name__ == "__main__": unittest.main()
