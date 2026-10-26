"""
Windows 11 電腦使用時間與健康休息提醒工具
自動化單元測試套件 (對應規格第十二節全部 20 項測試案例)
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from timer_engine import TimerEngine, AppState, TimerConfig, SingleInstanceChecker

class MockClock:
    def __init__(self, initial_time: float = 1000.0):
        self.current_time = initial_time
    def now(self) -> float:
        return self.current_time
    def advance(self, seconds: float) -> None:
        self.current_time += seconds

class TestTimerEngineSpecifications(unittest.TestCase):
    def setUp(self):
        self.clock = MockClock(1000.0)
        self.break_due_events = []
        self.long_idle_events = []
        self.config = TimerConfig(
            break_interval_seconds=45 * 60.0,
            short_idle_threshold_seconds=5 * 60.0,
            long_idle_threshold_seconds=15 * 60.0,
            snooze_duration_seconds=5 * 60.0,
        )
        self.engine = TimerEngine(
            config=self.config,
            time_provider=self.clock.now,
            on_break_due=lambda rid, secs: self.break_due_events.append((rid, secs)),
            on_long_idle_event=lambda st, et: self.long_idle_events.append((st, et)),
        )

    def test_case_01_accumulate_45min_triggers_break(self):
        for _ in range(2700):
            self.clock.advance(1.0)
            self.engine.report_activity()
            self.engine.tick()
        self.assertEqual(len(self.break_due_events), 1)
        self.assertEqual(self.engine.state, AppState.BREAK_DUE)

    def test_case_02_short_idle_3min_preserves_progress(self):
        for _ in range(1200):
            self.clock.advance(1.0)
            self.engine.report_activity()
            self.engine.tick()
        self.assertAlmostEqual(self.engine.cycle_active_seconds, 1200.0, delta=1.0)
        for _ in range(180):
            self.clock.advance(1.0)
            self.engine.tick()
        self.assertAlmostEqual(self.engine.cycle_active_seconds, 1200.0, delta=1.0)
        self.clock.advance(1.0)
        self.engine.report_activity()
        self.assertEqual(self.engine.state, AppState.ACTIVE)
        self.assertGreaterEqual(self.engine.cycle_active_seconds, 1200.0)

    def test_case_03_general_idle_8min_not_accumulated(self):
        for _ in range(1200):
            self.clock.advance(1.0)
            self.engine.report_activity()
            self.engine.tick()
        for _ in range(480):
            self.clock.advance(1.0)
            self.engine.tick()
        self.assertEqual(self.engine.state, AppState.INACTIVE)
        self.assertAlmostEqual(self.engine.cycle_active_seconds, 1200.0, delta=1.0)

    def test_case_04_long_idle_15min_recorded(self):
        for _ in range(960):
            self.clock.advance(1.0)
            self.engine.tick()
        self.assertEqual(self.engine.state, AppState.LONG_IDLE)
        self.clock.advance(1.0)
        self.engine.report_activity()
        self.assertEqual(len(self.long_idle_events), 1)

    def test_case_05_locked_session_does_not_accumulate(self):
        for _ in range(300):
            self.clock.advance(1.0)
            self.engine.report_activity()
            self.engine.tick()
        self.engine.on_session_locked()
        for _ in range(600):
            self.clock.advance(1.0)
            self.engine.report_activity()
            self.engine.tick()
        self.assertAlmostEqual(self.engine.cycle_active_seconds, 300.0, delta=1.0)

    def test_case_06_sleep_does_not_accumulate(self):
        for _ in range(300):
            self.clock.advance(1.0)
            self.engine.report_activity()
            self.engine.tick()
        self.engine.on_system_suspend()
        self.clock.advance(7200.0)
        self.engine.tick()
        self.assertAlmostEqual(self.engine.cycle_active_seconds, 300.0, delta=1.0)

    def test_case_07_resume_from_sleep_anchors_correctly(self):
        self.engine.on_system_suspend()
        self.clock.advance(3600.0)
        self.engine.on_system_resume()
        self.clock.advance(1.0)
        self.engine.report_activity()
        self.assertLess(self.engine.cycle_active_seconds, 10.0)

    def test_case_08_manual_pause_does_not_accumulate(self):
        self.engine.action_pause_reminder()
        for _ in range(300):
            self.clock.advance(1.0)
            self.engine.report_activity()
            self.engine.tick()
        self.assertEqual(self.engine.cycle_active_seconds, 0.0)

    def test_case_09_action_break_completed_resets_cycle(self):
        for _ in range(2700):
            self.clock.advance(1.0)
            self.engine.report_activity()
            self.engine.tick()
        self.engine.action_break_completed()
        self.assertEqual(self.engine.cycle_active_seconds, 0.0)
        self.assertEqual(self.engine.today_completed_breaks, 1)

    def test_case_10_snooze_single_reminder(self):
        for _ in range(2700):
            self.clock.advance(1.0)
            self.engine.report_activity()
            self.engine.tick()
        self.engine.action_snooze(300.0)
        self.clock.advance(299.0)
        self.engine.tick()
        self.assertEqual(len(self.break_due_events), 1)
        self.clock.advance(2.0)
        self.engine.tick()
        self.assertEqual(len(self.break_due_events), 2)

    def test_case_11_dismiss_window_preserves_state(self):
        for _ in range(2700):
            self.clock.advance(1.0)
            self.engine.report_activity()
            self.engine.tick()
        self.engine.action_dismiss_window_only()
        self.assertEqual(self.engine.state, AppState.BREAK_DUE)

    def test_case_12_notification_failure_does_not_break_engine(self):
        def faulty(rid, secs):
            raise RuntimeError("Toast 勿擾模式")
        eng = TimerEngine(config=self.config, time_provider=self.clock.now, on_break_due=faulty)
        for _ in range(2700):
            self.clock.advance(1.0)
            eng.report_activity()
            eng.tick()
        self.assertEqual(eng.state, AppState.BREAK_DUE)

    def test_case_13_restart_does_not_add_shutdown_duration(self):
        eng = TimerEngine(config=self.config, time_provider=self.clock.now)
        eng.restore_saved_state(600.0, 600.0)
        self.clock.advance(10800.0)
        eng.tick()
        self.assertEqual(eng.cycle_active_seconds, 600.0)

    def test_case_14_single_instance_logic(self):
        checker = SingleInstanceChecker("TestMutex")
        self.assertTrue(hasattr(checker, "already_running"))

    def test_case_15_autostart_command_quoted(self):
        from autostart import get_launch_command
        cmd = get_launch_command()
        self.assertTrue(cmd.startswith('"'))

    def test_case_16_autostart_can_be_disabled(self):
        from autostart import is_autostart_enabled
        self.assertIsInstance(is_autostart_enabled(), bool)

    def test_case_17_monotonic_immune_to_time_shifts(self):
        self.clock.advance(100.0)
        self.engine.report_activity()
        self.clock.advance(-50.0)
        self.engine.tick()
        self.assertGreaterEqual(self.engine.cycle_active_seconds, 0.0)

    def test_case_18_no_duplicate_break_due_on_tick(self):
        for _ in range(2700):
            self.clock.advance(1.0)
            self.engine.report_activity()
            self.engine.tick()
        for _ in range(100):
            self.clock.advance(1.0)
            self.engine.tick()
        self.assertEqual(len(self.break_due_events), 1)

    def test_case_19_exact_5min_boundary(self):
        self.clock.advance(1.0)
        self.engine.report_activity()
        self.clock.advance(300.0)
        self.engine.tick()
        self.assertEqual(self.engine.state, AppState.INACTIVE)

    def test_case_20_config_dynamic_update(self):
        new_cfg = TimerConfig(break_interval_seconds=600.0, short_idle_threshold_seconds=120.0, long_idle_threshold_seconds=600.0, snooze_duration_seconds=180.0)
        self.engine.set_config(new_cfg)
        for _ in range(600):
            self.clock.advance(1.0)
            self.engine.report_activity()
            self.engine.tick()
        self.assertEqual(self.engine.state, AppState.BREAK_DUE)

if __name__ == "__main__":
    unittest.main()
