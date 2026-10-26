"""
Windows 11 電腦使用時間與健康休息提醒工具
System Events: Windows 11 系統狀態偵測模組
"""

from __future__ import annotations
import sys
import ctypes
from ctypes import wintypes
import threading
from typing import Callable, Optional

WM_WTSSESSION_CHANGE = 0x02B1
WM_POWERBROADCAST = 0x0218
WM_DESTROY = 0x0002
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016

WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8
NOTIFY_FOR_THIS_SESSION = 0

PBT_APMSUSPEND = 0x0004
PBT_APMRESUMEAUTOMATIC = 0x0012
PBT_APMRESUMESUSPEND = 0x0007

class SystemEventListener:
    def __init__(
        self,
        on_locked: Optional[Callable[[], None]] = None,
        on_unlocked: Optional[Callable[[], None]] = None,
        on_suspend: Optional[Callable[[], None]] = None,
        on_resume: Optional[Callable[[], None]] = None,
        on_shutdown: Optional[Callable[[], None]] = None,
    ):
        self.on_locked = on_locked
        self.on_unlocked = on_unlocked
        self.on_suspend = on_suspend
        self.on_resume = on_resume
        self.on_shutdown = on_shutdown
        self._hwnd = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._is_windows = sys.platform.startswith("win")

    def start(self) -> None:
        if not self._is_windows or self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_message_pump, daemon=True, name="Win32SysEventPump")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._hwnd and self._is_windows:
            ctypes.windll.user32.PostMessageW(self._hwnd, WM_DESTROY, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run_message_pump(self) -> None:
        user32 = ctypes.windll.user32
        wtsapi32 = ctypes.windll.wtsapi32
        kernel32 = ctypes.windll.kernel32
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM)

        def _wnd_proc(hwnd, msg, wparam, lparam):
            if msg == WM_WTSSESSION_CHANGE:
                if wparam == WTS_SESSION_LOCK and self.on_locked:
                    self.on_locked()
                elif wparam == WTS_SESSION_UNLOCK and self.on_unlocked:
                    self.on_unlocked()
                return 0
            elif msg == WM_POWERBROADCAST:
                if wparam == PBT_APMSUSPEND and self.on_suspend:
                    self.on_suspend()
                elif wparam in (PBT_APMRESUMEAUTOMATIC, PBT_APMRESUMESUSPEND) and self.on_resume:
                    self.on_resume()
                return 1
            elif msg in (WM_QUERYENDSESSION, WM_ENDSESSION):
                if self.on_shutdown:
                    self.on_shutdown()
                return 1
            elif msg == WM_DESTROY:
                try:
                    wtsapi32.WTSUnRegisterSessionNotification(hwnd)
                except Exception:
                    pass
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._proc_delegate = WNDPROC(_wnd_proc)

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", ctypes.c_uint),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HCURSOR),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        class_name = "Win11BreakReminderHiddenClass"
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._proc_delegate
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.lpszClassName = class_name
        user32.RegisterClassW(ctypes.byref(wc))

        hwnd = user32.CreateWindowExW(0, class_name, "Win11BreakReminderMessageListener", 0, 0, 0, 0, 0, None, None, wc.hInstance, None)
        self._hwnd = hwnd
        try:
            wtsapi32.WTSRegisterSessionNotification(hwnd, NOTIFY_FOR_THIS_SESSION)
        except Exception:
            pass

        msg = wintypes.MSG()
        while self._running and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
