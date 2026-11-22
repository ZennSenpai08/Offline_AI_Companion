"""Owned Windows process group. Never discovers or kills processes by name."""
import ctypes
from ctypes import wintypes
import os
from threading import Lock

_JOBS = set()
_JOBS_LOCK = Lock()


class ProcessJob:
    def __init__(self):
        self.handle = None
        if os.name != "nt":
            return
        size_t = ctypes.c_size_t

        class Basic(ctypes.Structure):
            _fields_ = [("user", ctypes.c_int64), ("job_user", ctypes.c_int64),
                        ("flags", wintypes.DWORD), ("min_ws", size_t), ("max_ws", size_t),
                        ("active", wintypes.DWORD), ("affinity", size_t),
                        ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]

        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", ctypes.c_uint64 * 6),
                        ("process_memory", size_t), ("job_memory", size_t),
                        ("peak_process", size_t), ("peak_job", size_t)]

        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.SetInformationJobObject.restype = wintypes.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
        self.kernel.QueryInformationJobObject.restype = wintypes.BOOL
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error
        with _JOBS_LOCK:
            _JOBS.add(self)

    @staticmethod
    def owned_process_ids():
        """Native scoped enumeration for monitoring, avoiding global process scans."""
        result = set()
        with _JOBS_LOCK:
            for job in _JOBS:
                capacity = 16
                while capacity <= 1024:
                    class ProcessIds(ctypes.Structure):
                        _fields_ = [("assigned", wintypes.DWORD), ("returned", wintypes.DWORD),
                                    ("pids", ctypes.c_size_t * capacity)]
                    listing = ProcessIds()
                    ok = job.kernel.QueryInformationJobObject(job.handle, 3, ctypes.byref(listing), ctypes.sizeof(listing), None)
                    if ok and listing.returned >= listing.assigned:
                        result.update(listing.pids[:listing.returned])
                        break
                    error = ctypes.get_last_error()
                    if not ok and error != 234:  # ERROR_MORE_DATA
                        raise ctypes.WinError(error)
                    capacity = max(capacity * 2, listing.assigned)
                else:
                    raise RuntimeError("Owned process list exceeds monitoring bound")
        return result

    def assign(self, process):
        if self.handle and not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        with _JOBS_LOCK:
            _JOBS.discard(self)
            if self.handle:
                self.kernel.CloseHandle(self.handle)
                self.handle = None
