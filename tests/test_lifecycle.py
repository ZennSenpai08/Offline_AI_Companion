from pathlib import Path
import tempfile
import unittest

try:
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication
    QT_AVAILABLE = True
except ModuleNotFoundError:
    QT_AVAILABLE = False


@unittest.skipUnless(QT_AVAILABLE, "PySide6 unavailable: lifecycle integration NOT VERIFIED")
class LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_shutdown_saves_and_releases_then_restart_restores(self):
        from app.core.config import SettingsStore
        from app.main import CompanionController
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory))
            first = CompanionController(self.app, store)
            try:
                first.start()
                self.app.processEvents()
                first.overlay.set_character_scale(1.25)
                first.overlay.set_flipped(True)
                first.close()
                first.close()  # Idempotent cleanup.
                self.assertFalse(first.save_timer.isActive())
                self.assertFalse(first.hotkey.registered)
                self.assertFalse(first.controls.tray.isVisible())
                self.assertFalse(first.overlay.isVisible())
                self.assertEqual(store.load().scale, 1.25)
                second = CompanionController(self.app, store)
                try:
                    self.assertEqual(second.settings.scale, 1.25)
                    self.assertTrue(second.settings.flipped)
                    self.assertFalse(second.overlay.click_through)
                finally:
                    second.close()
                    second.overlay.deleteLater()
                    second.deleteLater()
            finally:
                first.close()
                first.overlay.deleteLater()
                first.deleteLater()
                self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__": unittest.main()
