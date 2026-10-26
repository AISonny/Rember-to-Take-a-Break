"""
Windows 11 電腦使用時間與健康休息提醒工具
Main: 程式總入口與各模組協調調度
"""

from __future__ import annotations
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Signal, QObject
from timer_engine import TimerEngine, AppState, TimerConfig, SingleInstanceChecker
from activity_monitor import ActivityMonitor
from system_events import SystemEventListener
from notification_service import NotificationService
from storage import SettingsStorage, HistoryStorage
from ui import MainWindow, BreakDialog
from tray import SystemTrayManager

class BridgeSignals(QObject):
    break_due = Signal(str, float)

def main():
    checker = SingleInstanceChecker()
    if checker.already_running:
        print("[資訊] 程式已經在背景執行中，請檢視系統匣圖示。")
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setApplicationName("Win11HealthBreakReminder")
    app.setQuitOnLastWindowClosed(False)

    settings_storage = SettingsStorage()
    history_storage = HistoryStorage()

    config = TimerConfig(
        break_interval_seconds=settings_storage.get("break_interval_minutes", 45) * 60.0,
        short_idle_threshold_seconds=settings_storage.get("short_idle_threshold_minutes", 5) * 60.0,
        long_idle_threshold_seconds=settings_storage.get("long_idle_threshold_minutes", 15) * 60.0,
        snooze_duration_seconds=settings_storage.get("snooze_duration_minutes", 5) * 60.0,
        enable_notifications=settings_storage.get("enable_notifications", True),
        enable_popup=settings_storage.get("enable_popup", True),
        enable_sound=settings_storage.get("enable_sound", True),
    )

    notifier = NotificationService(enable_sound=config.enable_sound)
    signals = BridgeSignals()
    break_dialog_instance = None

    def on_break_due_callback(reminder_id: str, active_seconds: float):
        signals.break_due.emit(reminder_id, active_seconds)

    engine = TimerEngine(
        config=config,
        on_break_due=on_break_due_callback,
    )

    today_stats = history_storage.get_today_stats()
    engine.restore_saved_state(cycle_seconds=0.0, today_seconds=today_stats.get("active_seconds", 0.0))

    main_window = MainWindow(engine, settings_storage, history_storage)
    tray_manager = SystemTrayManager(main_window, engine)

    def handle_break_due_ui(reminder_id: str, active_seconds: float):
        nonlocal break_dialog_instance
        if config.enable_notifications:
            notifier.send_break_notification()
        if config.enable_popup:
            if break_dialog_instance is None or not break_dialog_instance.isVisible():
                break_dialog_instance = BreakDialog(engine, main_window)
                break_dialog_instance.show()

    signals.break_due.connect(handle_break_due_ui)

    monitor = ActivityMonitor(on_activity_detected=engine.report_activity)
    monitor.start()

    sys_listener = SystemEventListener(
        on_locked=engine.on_session_locked,
        on_unlocked=engine.on_session_unlocked,
        on_suspend=engine.on_system_suspend,
        on_resume=engine.on_system_resume,
    )
    sys_listener.start()

    engine_timer = QTimer()
    engine_timer.timeout.connect(engine.tick)
    engine_timer.start(1000)

    if "--minimized" not in sys.argv:
        main_window.show()

    exit_code = app.exec()
    engine.stop()
    monitor.stop()
    sys_listener.stop()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
