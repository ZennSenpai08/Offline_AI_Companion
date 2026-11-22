"""Native property/message checks, not human desktop acceptance tests."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import tempfile
import unittest

try:
    from PySide6.QtCore import QEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    QT_AVAILABLE = True
except ModuleNotFoundError:
    QT_AVAILABLE = False


@unittest.skipUnless(QT_AVAILABLE and sys.platform == "win32", "Requires Windows and Qt")
class WindowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        if cls.app.platformName() != "windows":
            raise unittest.SkipTest("Native HWND tests require the Windows Qt plugin")

    def setUp(self):
        from app.core.config import SettingsStore
        from app.main import CompanionController
        self.directory = tempfile.TemporaryDirectory()
        self.controller = CompanionController(self.app, SettingsStore(Path(self.directory.name)))
        self.controller.start()
        self.app.processEvents()
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t

    def tearDown(self):
        self.controller.close()
        self.controller.overlay.deleteLater()
        self.controller.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.directory.cleanup()

    def exstyle(self):
        self.app.processEvents()
        return self.user32.GetWindowLongPtrW(int(self.controller.overlay.winId()), -20)

    def test_native_layered_tool_topmost_and_input_styles(self):
        overlay = self.controller.overlay
        self.assertTrue(self.exstyle() & 0x80000)  # WS_EX_LAYERED
        self.assertTrue(self.exstyle() & 0x80)  # WS_EX_TOOLWINDOW
        self.assertTrue(self.exstyle() & 0x8)  # WS_EX_TOPMOST
        overlay.set_always_on_top(False)
        self.assertFalse(self.exstyle() & 0x8)
        overlay.set_always_on_top(True)
        self.assertTrue(self.exstyle() & 0x8)
        self.assertTrue(overlay.set_click_through(True))
        self.assertTrue(self.exstyle() & 0x20)  # WS_EX_TRANSPARENT
        self.controller.controls.menu.actions()[0].trigger()
        self.assertFalse(self.exstyle() & 0x20)

    def test_registered_hotkey_message_recovers_through_native_event_loop(self):
        controller = self.controller
        self.assertTrue(controller.hotkey.registered, "Close other companion instances/hotkey owners before this test")
        self.assertTrue(controller.overlay.set_click_through(True))
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        self.user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.user32.PostThreadMessageW.restype = wintypes.BOOL
        # Post to this test's GUI thread only. This verifies native dispatch, not
        # physical keyboard delivery or conflict handling in another application.
        self.assertTrue(self.user32.PostThreadMessageW(kernel32.GetCurrentThreadId(), 0x0312, controller.hotkey.IDENTIFIER, 0))
        QTest.qWait(100)
        self.assertFalse(controller.overlay.click_through)

    def test_native_silhouette_and_dimensions_at_current_monitor_dpi(self):
        overlay = self.controller.overlay
        hwnd = int(overlay.winId())
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        gdi32.CreateRectRgn.argtypes = [ctypes.c_int] * 4
        gdi32.CreateRectRgn.restype = wintypes.HANDLE
        gdi32.PtInRegion.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_int]
        gdi32.PtInRegion.restype = wintypes.BOOL
        gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
        self.user32.GetWindowRgn.argtypes = [wintypes.HWND, wintypes.HANDLE]
        self.user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        region = gdi32.CreateRectRgn(0, 0, 0, 0)
        self.assertTrue(region)
        try:
            self.assertEqual(self.user32.GetWindowRgn(hwnd, region), 3)  # COMPLEXREGION
            self.assertFalse(gdi32.PtInRegion(region, 1, 1))
            dpr = overlay.devicePixelRatioF()
            self.assertTrue(gdi32.PtInRegion(region, round(120 * dpr), round(140 * dpr)))
            rect = wintypes.RECT()
            self.assertTrue(self.user32.GetWindowRect(hwnd, ctypes.byref(rect)))
            self.assertAlmostEqual(rect.right - rect.left, overlay.width() * dpr, delta=1)
            self.assertAlmostEqual(rect.bottom - rect.top, overlay.height() * dpr, delta=1)
        finally:
            gdi32.DeleteObject(region)


if __name__ == "__main__":
    unittest.main()
