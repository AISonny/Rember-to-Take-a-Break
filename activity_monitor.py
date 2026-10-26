"""
Windows 11 電腦使用時間與健康休息提醒工具
Activity Monitor: 電腦活動與閒置狀態偵測模組
"""

from __future__ import annotations
import sys
import time
import ctypes
import threading
from typing import Callable, Optional

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("dwTime", ctypes.c_uint),
    ]

class ActivityMonitor:
    def __init__(
        self,
        on_activity_detected: Callable[[], None],
        poll_interval_seconds: float = 1.0,
        idle_activity_threshold_seconds: float = 1.0,
    ):
        self.on_activity_detected = on_activity_detected
        self.poll_interval_seconds = poll_interval_seconds
        self.idle_activity_threshold_seconds = idle_activity_threshold_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._is_windows = sys.platform.startswith("win")
        if self._is_windows:
            self._user32 = ctypes.windll.user32
            self._kernel32 = ctypes.windll.kernel32
        else:
            self._user32 = None
            self._kernel32 = None

    def get_idle_seconds(self) -> float:
        if not self._is_windows or not self._user32:
            return 0.0
        try:
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if self._user32.GetLastInputInfo(ctypes.byref(lii)):
                current_tick = self._kernel32.GetTickCount64()
                dw_time = lii.dwTime
                idle_ms = (current_tick & 0xFFFFFFFF) - dw_time
                if idle_ms < 0:
                    idle_ms += 0x100000000
                return max(0.0, idle_ms / 1000.0)
        except Exception:
            pass
        return 0.0

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="ActivityMonitorThread")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _monitor_loop(self) -> None:
        last_reported_idle = 999999.0
        while self._running:
            idle_sec = self.get_idle_seconds()
            if idle_sec < self.idle_activity_threshold_seconds or idle_sec < last_reported_idle - 0.5:
                try:
                    self.on_activity_detected()
                except Exception:
                    pass
            last_reported_idle = idle_sec
            time.sleep(self.poll_interval_seconds)
