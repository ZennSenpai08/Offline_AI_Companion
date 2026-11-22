"""Qt integration tests. No native mouse injection or other application access.

Use QT_QPA_PLATFORM=offscreen for headless tests. Native Windows composition,
tray visibility and cross-process click routing still need the manual checklist.
"""
from pathlib import Path
import tempfile
import unittest

try:
    from PySide6.QtCore import QEvent, QPoint, QPointF, QSize, Qt
    from PySide6.QtGui import QImage, QMouseEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    QT_AVAILABLE = True
except ModuleNotFoundError:
    QT_AVAILABLE = False


@unittest.skipUnless(QT_AVAILABLE, "PySide6 unavailable: desktop integration NOT VERIFIED")
class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        from app.avatar.placeholder import PlaceholderRenderer
        from app.core.config import Settings
        from app.desktop.overlay import Overlay
        self.renderer = PlaceholderRenderer()
        self.overlay = Overlay(Settings(), self.renderer)
        self.overlay.show()
        self.app.processEvents()

    def tearDown(self):
        self.overlay.close()
        self.overlay.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.renderer.close()

    def test_frameless_translucent_and_silhouette_mask(self):
        self.assertTrue(self.overlay.windowFlags() & Qt.WindowType.FramelessWindowHint)
        self.assertTrue(self.overlay.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        self.assertFalse(self.overlay.mask().contains(QPoint(0, 0)))
        self.assertTrue(self.overlay.hit_test(QPoint(120, 140)))
        self.assertFalse(self.overlay.hit_test(QPoint(0, 0)))
        self.assertEqual(self.overlay._image.pixelColor(0, 0).alpha(), 0)
        self.assertGreater(self.overlay._image.pixelColor(self.overlay._image.width() // 2, self.overlay._image.height() // 2).alpha(), 0)

    def test_topmost_flag_changes_without_losing_position(self):
        position = self.overlay.pos()
        self.overlay.set_always_on_top(False)
        self.assertFalse(self.overlay.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.assertEqual(position, self.overlay.pos())
        self.overlay.set_always_on_top(True)
        self.assertTrue(self.overlay.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)

    def test_sizes_keep_proportions_and_clear_corners(self):
        for scale in (0.5, 0.75, 1.0, 1.25, 1.5, 2):
            self.overlay.set_character_scale(scale)
            self.assertLessEqual(abs(self.overlay.width() * 1.5 - self.overlay.height()), 1)
            self.assertFalse(self.overlay.mask().contains(QPoint(0, 0)))

    def test_click_through_requires_recovery_and_can_be_recovered(self):
        warnings = []
        self.overlay.warning.connect(warnings.append)
        self.assertFalse(self.overlay.set_click_through(True))
        self.assertFalse(self.overlay.click_through)
        self.assertEqual(len(warnings), 1)
        self.overlay.can_recover = lambda: True
        self.assertTrue(self.overlay.set_click_through(True))
        self.assertTrue(self.overlay.windowFlags() & Qt.WindowType.WindowTransparentForInput)
        self.assertFalse(self.overlay.hit_test(QPoint(120, 140)))
        self.overlay.recover()
        self.assertFalse(self.overlay.click_through)
        self.assertFalse(self.overlay.windowFlags() & Qt.WindowType.WindowTransparentForInput)

    def test_drag_events_from_visible_character(self):
        self.overlay.move(100, 100)
        start = self.overlay.pos()
        local = QPointF(120, 140)
        global_start = QPointF(self.overlay.mapToGlobal(local.toPoint()))
        events = (
            (QEvent.Type.MouseButtonPress, QPointF(), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton),
            (QEvent.Type.MouseMove, QPointF(60, 35), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton),
            (QEvent.Type.MouseButtonRelease, QPointF(60, 35), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton),
        )
        # Construct and dispatch in order: Qt 6 mouse events share pointing-device
        # state, so constructing future events can change an earlier event's position.
        for kind, offset, button, buttons in events:
            event = QMouseEvent(kind, local, global_start + offset, button, buttons, Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(self.overlay, event)
        self.assertEqual(self.overlay.pos(), start + QPoint(60, 35))

    def test_drag_cannot_start_in_empty_corner(self):
        start = self.overlay.pos()
        # QPoint(0, 0) is QTest's default-position sentinel (the widget center).
        self.assertFalse(self.overlay.hit_test(QPoint(1, 1)))
        QTest.mousePress(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(1, 1))
        QTest.mouseMove(self.overlay, QPoint(20, 20))
        QTest.mouseRelease(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
        self.assertEqual(self.overlay.pos(), start)

    def test_render_at_different_pixel_densities(self):
        for dpr in (1.0, 1.25, 1.5, 2.0):
            image = self.renderer.render(QSize(240, 360), dpr)
            self.assertEqual(image.size(), QSize(round(240 * dpr), round(360 * dpr)))
            self.assertEqual(image.devicePixelRatio(), dpr)
            self.assertEqual(image.pixelColor(0, 0).alpha(), 0)

    def test_mirroring_changes_asymmetric_accessory(self):
        normal = self.renderer.render(QSize(240, 360), 1)
        mirrored = self.renderer.render(QSize(240, 360), 1, True)
        self.assertNotEqual(normal, mirrored)

    def test_persist_and_recreate_overlay(self):
        from app.core.config import SettingsStore
        from app.desktop.overlay import Overlay
        self.overlay.set_character_scale(0.75)
        self.overlay.set_flipped(True)
        self.overlay.move(120, 150)
        self.overlay.settle_position()
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory))
            store.save(self.overlay.settings)
            restored = Overlay(store.load(), self.renderer)
            try:
                self.assertEqual(restored.pos(), self.overlay.pos())
                self.assertEqual(restored.size(), self.overlay.size())
                self.assertTrue(restored.settings.flipped)
                self.assertFalse(restored.click_through)
            finally:
                restored.deleteLater()
                self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_tray_actions_use_real_window_operations(self):
        from PySide6.QtGui import QIcon, QPixmap
        from app.desktop.tray import DesktopControls
        controls = DesktopControls(self.overlay, QIcon(QPixmap.fromImage(self.overlay._image)))
        exits = []
        controls.exit_requested.connect(lambda: exits.append(True))
        try:
            controls.top_action.trigger()
            self.assertFalse(self.overlay.settings.always_on_top)
            controls.size_actions[0].trigger()
            self.assertEqual(self.overlay.settings.scale, 0.5)
            controls.exit_action.trigger()
            self.assertEqual(exits, [True])
        finally:
            controls.close()


if __name__ == "__main__": unittest.main()
