from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import sys
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QTimer
from PySide6.QtWidgets import QApplication

LOG = logging.getLogger(__name__)


class RecoveryHotkey(QAbstractNativeEventFilter):
    """Ctrl+Alt+Shift+R, bound to the GUI thread rather than a recreated HWND."""

    IDENTIFIER = 0x4C41
    LABEL = "Ctrl+Alt+Shift+R"

    def __init__(self, application: QApplication, callback: Callable[[], None]):
        super().__init__()
        self.application = application
        self.callback = callback
        self.registered = False
        self._user32 = None
        if sys.platform == "win32" and application.platformName() == "windows":
            self._user32 = ctypes.WinDLL("user32", use_last_error=True)
            self._user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            self._user32.RegisterHotKey.restype = wintypes.BOOL
            self._user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            self._user32.UnregisterHotKey.restype = wintypes.BOOL
            self.registered = bool(self._user32.RegisterHotKey(None, self.IDENTIFIER, 0x0002 | 0x0001 | 0x0004 | 0x4000, ord("R")))
            if self.registered:
                application.installNativeEventFilter(self)
            else:
                LOG.warning("Recovery hotkey unavailable (Windows error %s); tray recovery remains available.", ctypes.get_last_error())

    def nativeEventFilter(self, event_type, message):
        if self.registered and bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            event = wintypes.MSG.from_address(int(message))
            if event.message == 0x0312 and event.wParam == self.IDENTIFIER:
                QTimer.singleShot(0, self.callback)
                return True, 0
        return False, 0

    def close(self) -> None:
        if self.registered:
            self.application.removeNativeEventFilter(self)
            if not self._user32.UnregisterHotKey(None, self.IDENTIFIER):
                LOG.warning("Could not unregister recovery hotkey: %s", ctypes.get_last_error())
            self.registered = False
