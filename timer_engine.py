"""
Windows 11 電腦使用時間與健康休息提醒工具
Timer Engine: 核心計時引擎與狀態機

依據規格：
1. 僅累積符合定義的有效電腦活動時間。
2. 使用 time.monotonic() 確保時鐘單調遞增，免疫系統時間校時或夏令時漂移。
3. 嚴格實作三段式閒置判定與容錯（短暫閒置容錯 5 分鐘，長時間閒置 15 分鐘）。
4. 閒置期間（短暫閒置、一般閒置、長時間閒置）一律不累積時間，保留既有進度。
5. 支援 11 種狀態機切換與邊界保護。
"""

from __future__ import annotations
import enum
import time
import uuid
import threading
from typing import Callable, Optional, Dict, Any


class AppState(enum.Enum):
    """應用程式 11 種核心狀態"""
    ACTIVE = "ACTIVE"              # 有符合條件的電腦活動，累積時間中
    SHORT_IDLE = "SHORT_IDLE"      # 短暫閒置（<5m），保留進度，不增加時間
    INACTIVE = "INACTIVE"          # 超過閒置門檻（>=5m 且 <15m），暫停累積
    LONG_IDLE = "LONG_IDLE"        # 超過長時間門檻（>=15m），暫停累積並記錄事件
    BREAK_DUE = "BREAK_DUE"        # 45分鐘提醒已觸發，等待使用者處置
    BREAK_PAUSED = "BREAK_PAUSED"  # 使用者確認「我正在休息」，暫停累積保留進度
    PAUSED = "PAUSED"              # 使用者手動暫停工具
    LOCKED = "LOCKED"              # Windows 工作階段鎖定中
    SUSPENDED = "SUSPENDED"        # 系統進入睡眠或休眠
    RESUMING = "RESUMING"          # 系統剛恢復，重新校正時間基準
    STOPPED = "STOPPED"            # 程式正在結束或已停止


class TimerConfig:
    """計時引擎參數設定"""
    def __init__(
        self,
        break_interval_seconds: float = 45 * 60.0,       # 預設 45 分鐘
        short_idle_threshold_seconds: float = 5 * 60.0,  # 預設 5 分鐘
        long_idle_threshold_seconds: float = 15 * 60.0,  # 預設 15 分鐘
        snooze_duration_seconds: float = 5 * 60.0,       # 預設 5 分鐘
        active_burst_window_seconds: float = 2.0,        # 連續輸入判定窗口 (2秒)
        enable_notifications: bool = True,
        enable_popup: bool = True,
        enable_sound: bool = True,
    ):
        if long_idle_threshold_seconds < short_idle_threshold_seconds:
            raise ValueError("長時間閒置門檻不得小於短暫閒置門檻")
        if break_interval_seconds <= 0 or short_idle_threshold_seconds <= 0:
            raise ValueError("時間間隔必須大於 0")

        self.break_interval_seconds = break_interval_seconds
        self.short_idle_threshold_seconds = short_idle_threshold_seconds
        self.long_idle_threshold_seconds = long_idle_threshold_seconds
        self.snooze_duration_seconds = snooze_duration_seconds
        self.active_burst_window_seconds = active_burst_window_seconds
        self.enable_notifications = enable_notifications
        self.enable_popup = enable_popup
        self.enable_sound = enable_sound


class TimerEngine:
    """核心計時引擎"""
    def __init__(
        self,
        config: Optional[TimerConfig] = None,
        time_provider: Optional[Callable[[], float]] = None,
        on_break_due: Optional[Callable[[str, float], None]] = None,
        on_state_changed: Optional[Callable[[AppState, AppState], None]] = None,
        on_long_idle_event: Optional[Callable[[float, float], None]] = None,
    ):
        self.config = config or TimerConfig()
        self._get_time = time_provider or time.monotonic
        self._lock = threading.RLock()

        self.on_break_due = on_break_due
        self.on_state_changed = on_state_changed
        self.on_long_idle_event = on_long_idle_event

        self._state = AppState.ACTIVE
        self._previous_state = AppState.ACTIVE

        now = self._get_time()
        self._last_activity_time = now
        self._last_tick_time = now
        self._cycle_active_seconds = 0.0
        self._today_active_seconds = 0.0

        self._today_reminder_count = 0
        self._today_completed_breaks = 0
        self._today_snooze_count = 0

        self._current_reminder_id: Optional[str] = None
        self._snooze_until: Optional[float] = None
        self._long_idle_start_time: Optional[float] = None
        self._has_logged_current_long_idle = False

    @property
    def state(self) -> AppState:
        with self._lock:
            return self._state

    @property
    def cycle_active_seconds(self) -> float:
        with self._lock:
            return self._cycle_active_seconds

    @property
    def remaining_seconds_to_break(self) -> float:
        with self._lock:
            remaining = self.config.break_interval_seconds - self._cycle_active_seconds
            return max(0.0, remaining)

    @property
    def today_active_seconds(self) -> float:
        with self._lock:
            return self._today_active_seconds

    @property
    def today_reminder_count(self) -> int:
        with self._lock:
            return self._today_reminder_count

    @property
    def today_completed_breaks(self) -> int:
        with self._lock:
            return self._today_completed_breaks

    def set_config(self, new_config: TimerConfig) -> None:
        with self._lock:
            self.config = new_config

    def _transition_to(self, new_state: AppState) -> None:
        if self._state == new_state:
            return
        old_state = self._state
        self._previous_state = old_state
        self._state = new_state
        if self.on_state_changed:
            try:
                self.on_state_changed(old_state, new_state)
            except Exception:
                pass

    def report_activity(self) -> None:
        with self._lock:
            now = self._get_time()

            if self._state in (
                AppState.LOCKED,
                AppState.SUSPENDED,
                AppState.PAUSED,
                AppState.BREAK_PAUSED,
                AppState.BREAK_DUE,
                AppState.STOPPED,
            ):
                self._last_activity_time = now
                self._last_tick_time = now
                return

            if self._state == AppState.RESUMING:
                self._last_activity_time = now
                self._last_tick_time = now
                self._transition_to(AppState.ACTIVE)
                return

            if self._state == AppState.LONG_IDLE and self._long_idle_start_time is not None:
                if self.on_long_idle_event:
                    try:
                        self.on_long_idle_event(self._long_idle_start_time, now)
                    except Exception:
                        pass
                self._long_idle_start_time = None
                self._has_logged_current_long_idle = False

            interval = max(0.0, now - self._last_activity_time)
            burst_window = self.config.active_burst_window_seconds

            if self._state == AppState.ACTIVE:
                if interval <= burst_window:
                    self._accumulate_time(interval)
                    if self._cycle_active_seconds >= self.config.break_interval_seconds:
                        self._trigger_break_reminder()
            else:
                self._transition_to(AppState.ACTIVE)

            self._last_activity_time = now
            self._last_tick_time = now

    def tick(self) -> None:
        with self._lock:
            now = self._get_time()
            idle_seconds = max(0.0, now - self._last_activity_time)
            short_th = self.config.short_idle_threshold_seconds
            long_th = self.config.long_idle_threshold_seconds
            burst_window = self.config.active_burst_window_seconds

            if self._snooze_until is not None and now >= self._snooze_until:
                self._snooze_until = None
                if self._state not in (AppState.LOCKED, AppState.SUSPENDED, AppState.PAUSED, AppState.STOPPED):
                    self._trigger_break_reminder()
                    self._last_tick_time = now
                    return

            if self._state == AppState.ACTIVE:
                if idle_seconds > burst_window and idle_seconds < short_th:
                    self._transition_to(AppState.SHORT_IDLE)
                elif idle_seconds >= short_th and idle_seconds < long_th:
                    self._transition_to(AppState.INACTIVE)
                elif idle_seconds >= long_th:
                    if not self._has_logged_current_long_idle:
                        self._long_idle_start_time = self._last_activity_time + short_th
                        self._has_logged_current_long_idle = True
                    self._transition_to(AppState.LONG_IDLE)

            elif self._state == AppState.SHORT_IDLE:
                if idle_seconds >= short_th and idle_seconds < long_th:
                    self._transition_to(AppState.INACTIVE)
                elif idle_seconds >= long_th:
                    if not self._has_logged_current_long_idle:
                        self._long_idle_start_time = self._last_activity_time + short_th
                        self._has_logged_current_long_idle = True
                    self._transition_to(AppState.LONG_IDLE)

            elif self._state == AppState.INACTIVE:
                if idle_seconds >= long_th:
                    if not self._has_logged_current_long_idle:
                        self._long_idle_start_time = self._last_activity_time + short_th
                        self._has_logged_current_long_idle = True
                    self._transition_to(AppState.LONG_IDLE)

            self._last_tick_time = now

    def _accumulate_time(self, seconds: float) -> None:
        if seconds <= 0:
            return
        self._cycle_active_seconds += seconds
        self._today_active_seconds += seconds

    def _trigger_break_reminder(self) -> None:
        if self._state == AppState.BREAK_DUE:
            return
        self._transition_to(AppState.BREAK_DUE)
        reminder_id = f"break-{uuid.uuid4().hex[:8]}"
        self._current_reminder_id = reminder_id
        self._today_reminder_count += 1
        if self.on_break_due:
            try:
                self.on_break_due(reminder_id, self._cycle_active_seconds)
            except Exception:
                pass

    def action_break_completed(self) -> None:
        with self._lock:
            self._cycle_active_seconds = 0.0
            self._current_reminder_id = None
            self._snooze_until = None
            self._today_completed_breaks += 1
            now = self._get_time()
            self._last_activity_time = now
            self._last_tick_time = now
            if self._state in (AppState.BREAK_DUE, AppState.BREAK_PAUSED):
                self._transition_to(AppState.ACTIVE)

    def action_snooze(self, custom_seconds: Optional[float] = None) -> None:
        with self._lock:
            snooze_sec = custom_seconds or self.config.snooze_duration_seconds
            now = self._get_time()
            self._snooze_until = now + snooze_sec
            self._current_reminder_id = None
            self._today_snooze_count += 1
            self._transition_to(AppState.SHORT_IDLE)

    def action_resting_now(self) -> None:
        with self._lock:
            self._current_reminder_id = None
            self._transition_to(AppState.BREAK_PAUSED)

    def action_end_resting(self) -> None:
        with self._lock:
            if self._state == AppState.BREAK_PAUSED:
                now = self._get_time()
                self._last_activity_time = now
                self._last_tick_time = now
                self._transition_to(AppState.ACTIVE)

    def action_dismiss_window_only(self) -> None:
        pass

    def action_pause_reminder(self) -> None:
        with self._lock:
            self._current_reminder_id = None
            self._transition_to(AppState.PAUSED)

    def action_resume(self) -> None:
        with self._lock:
            if self._state == AppState.PAUSED:
                now = self._get_time()
                self._last_activity_time = now
                self._last_tick_time = now
                self._transition_to(AppState.ACTIVE)

    def manual_mark_phone_use(self) -> None:
        with self._lock:
            if self._state in (AppState.ACTIVE, AppState.SHORT_IDLE):
                self._transition_to(AppState.SHORT_IDLE)

    def on_session_locked(self) -> None:
        with self._lock:
            if self._state not in (AppState.STOPPED, AppState.SUSPENDED):
                self._transition_to(AppState.LOCKED)

    def on_session_unlocked(self) -> None:
        with self._lock:
            if self._state == AppState.LOCKED:
                now = self._get_time()
                self._last_activity_time = now
                self._last_tick_time = now
                self._transition_to(AppState.RESUMING)

    def on_system_suspend(self) -> None:
        with self._lock:
            if self._state != AppState.STOPPED:
                self._transition_to(AppState.SUSPENDED)

    def on_system_resume(self) -> None:
        with self._lock:
            if self._state == AppState.SUSPENDED:
                now = self._get_time()
                self._last_activity_time = now
                self._last_tick_time = now
                self._transition_to(AppState.RESUMING)

    def stop(self) -> None:
        with self._lock:
            self._transition_to(AppState.STOPPED)

    def restore_saved_state(self, cycle_seconds: float, today_seconds: float) -> None:
        with self._lock:
            self._cycle_active_seconds = max(0.0, cycle_seconds)
            self._today_active_seconds = max(0.0, today_seconds)
            now = self._get_time()
            self._last_activity_time = now
            self._last_tick_time = now


class SingleInstanceChecker:
    def __init__(self, name: str = "Local\\Win11HealthBreakReminderSingleInstanceMutex"):
        import sys
        self.name = name
        self.mutex = None
        self.already_running = False
        if sys.platform.startswith("win"):
            import ctypes
            kernel32 = ctypes.windll.kernel32
            ERROR_ALREADY_EXISTS = 183
            self.mutex = kernel32.CreateMutexW(None, False, self.name)
            last_error = kernel32.GetLastError()
            if last_error == ERROR_ALREADY_EXISTS:
                self.already_running = True
