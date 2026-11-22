"""Per-settings-directory ownership; QLockFile remains the locking authority.

Process inspection is diagnostic only. Never unlink locks or terminate processes
based on a PID read from disk. Qt performs its own atomic stale-lock recovery.
"""
from __future__ import annotations

from pathlib import Path
import stat
import sys

from PySide6.QtCore import QLockFile, QSysInfo


class InstanceLockError(RuntimeError):
    def __init__(self, kind: str, title: str, detail: str, path: Path):
        self.kind = kind
        self.title = title
        self.path = path
        super().__init__(f"{detail}\n\nLock file: {path}\nSettings folder: {path.parent}")


class SingleInstance:
    def __init__(self, directory: Path):
        self.path = directory.resolve() / "application.lock"
        self.lock = QLockFile(str(self.path))
        # A companion can run indefinitely. Age alone must never steal its lock.
        # Zero disables the age threshold, not Qt's dead-process detection.
        self.lock.setStaleLockTime(0)

    def __enter__(self) -> SingleInstance:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError as exc:
            raise InstanceLockError("permission", "Settings folder access denied",
                                    f"Windows denied access to the settings folder: {exc}. Check this folder's permissions.", self.path) from exc
        except OSError as exc:
            raise InstanceLockError("filesystem", "Cannot prepare settings folder", str(exc), self.path) from exc
        if self.path.is_dir():
            raise InstanceLockError("filesystem", "Invalid lock path",
                                    "A directory occupies the required lock-file path. Its contents were not changed.", self.path)
        if not self.lock.tryLock(100):
            raise self._failure()
        return self

    def _failure(self) -> InstanceLockError:
        error = self.lock.error()
        if error == QLockFile.LockError.PermissionError:
            return InstanceLockError("permission", "Cannot create instance lock",
                                     "Qt reported PermissionError: access to create the lock file was denied. "
                                     "Check folder/lock-file permissions and read-only status. No running instance has been inferred from this error.", self.path)
        if error != QLockFile.LockError.LockFailedError:
            return InstanceLockError("filesystem", "Cannot write instance lock",
                                     f"Qt reported {error.name}. Check available disk space and filesystem errors. "
                                     "This is not a confirmed duplicate instance.", self.path)
        # PySide6 returns (pid, hostname, application name), without a bool prefix.
        pid, hostname, application = self.lock.getLockInfo()
        if pid <= 0:
            return InstanceLockError("unverified", "Instance lock owner unavailable",
                                     "The lock is busy or its owner record is unreadable/incomplete. Another launch may be starting. "
                                     "Wait briefly and retry. The lock was preserved because ownership could not be verified.", self.path)
        owner = f"Recorded owner: PID {pid}, application {application!r}, computer {hostname!r}."
        if hostname.casefold() != QSysInfo.machineHostName().casefold():
            return InstanceLockError("unverified", "Instance lock belongs to another computer",
                                     f"{owner}\nLocal process inspection cannot verify this owner. The lock was preserved.", self.path)
        # Imported only on lock contention; normal desktop startup needs no psutil.
        import psutil
        try:
            process_name = Path(psutil.Process(pid).name()).stem
        except psutil.NoSuchProcess:
            # Windows also reports LockFailedError when a dead owner's existing
            # lock cannot be removed because its read-only attribute is set.
            try:
                readonly = sys.platform == "win32" and self.path.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY
            except OSError:
                readonly = False  # Ownership/file state may change concurrently.
            if readonly:
                return InstanceLockError("permission", "Stale lock is read-only",
                                         f"{owner}\nThat PID is no longer running. The lock file has Windows' read-only attribute, "
                                         "which prevents Qt from recovering it. Correct that file's read-only setting, then retry. "
                                         "The file and your settings were preserved.", self.path)
            return InstanceLockError("stale", "Stale instance lock could not be recovered",
                                     f"{owner}\nThat PID is no longer running, but Qt could not acquire/recover the lock. "
                                     "Retry; if this persists, check directory and lock-file permissions. No forced deletion was attempted.", self.path)
        except psutil.AccessDenied:
            return InstanceLockError("unverified", "Instance lock owner cannot be inspected",
                                     f"{owner}\nWindows denied process inspection. The lock was preserved; use the existing tray if available.", self.path)
        if process_name.casefold() != Path(application).stem.casefold():
            return InstanceLockError("unverified", "Instance lock owner identity changed",
                                     f"{owner}\nThe current process name differs from the record. Retry to allow Qt to recheck ownership. "
                                     "No process was stopped and no lock was forcibly removed.", self.path)
        return InstanceLockError("active", "Companion already running",
                                 f"A running process owns this settings-folder lock. {owner}\n\n"
                                 "Use the existing companion's tray icon (including Windows tray overflow), or press Ctrl+Alt+Shift+R "
                                 "if its recovery hotkey registered. To restart with updated code, choose Exit application from that tray, "
                                 "then run the same command again. This second launch has not changed your settings.", self.path)

    def close(self) -> None:
        if self.lock.isLocked():
            self.lock.unlock()

    def __exit__(self, *_exc) -> None:
        self.close()
