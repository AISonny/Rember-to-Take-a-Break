"""
Windows 11 電腦使用時間與健康休息提醒工具
Storage: 本機設定檔（JSON 原子寫入）與歷史紀錄（SQLite）儲存模組
"""

from __future__ import annotations
import os
import json
import sqlite3
import datetime
import tempfile
from typing import Dict, Any, Optional, List

def get_app_data_dir() -> str:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        app_dir = os.path.join(local_app_data, "Win11BreakReminder")
    else:
        app_dir = os.path.join(os.path.expanduser("~"), ".win11_break_reminder")
    os.makedirs(app_dir, exist_ok=True)
    return app_dir

class SettingsStorage:
    DEFAULT_SETTINGS: Dict[str, Any] = {
        "break_interval_minutes": 45,
        "short_idle_threshold_minutes": 5,
        "long_idle_threshold_minutes": 15,
        "snooze_duration_minutes": 5,
        "enable_notifications": True,
        "enable_popup": True,
        "enable_sound": True,
        "auto_start": False,
        "show_daily_stats": True,
        "keep_history": True,
    }

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = data_dir or get_app_data_dir()
        self.config_path = os.path.join(self.data_dir, "config.json")
        self._settings = self.load()

    def load(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            self.save(self.DEFAULT_SETTINGS)
            return dict(self.DEFAULT_SETTINGS)
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = dict(self.DEFAULT_SETTINGS)
                merged.update(data)
                return merged
        except Exception:
            return dict(self.DEFAULT_SETTINGS)

    def save(self, settings: Dict[str, Any]) -> None:
        self._settings = settings
        dir_name = os.path.dirname(self.config_path)
        with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
            json.dump(settings, tf, indent=2, ensure_ascii=False)
            temp_path = tf.name
        os.replace(temp_path, self.config_path)

    def get(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._settings[key] = value
        self.save(self._settings)

class HistoryStorage:
    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = data_dir or get_app_data_dir()
        self.db_path = os.path.join(self.data_dir, "history.db")
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_stats (
                    date TEXT PRIMARY KEY,
                    active_seconds REAL DEFAULT 0,
                    reminders_count INTEGER DEFAULT 0,
                    completed_breaks INTEGER DEFAULT 0,
                    snooze_count INTEGER DEFAULT 0,
                    long_idle_count INTEGER DEFAULT 0,
                    last_updated TEXT
                )
            """)
            conn.commit()

    def get_today_stats(self) -> Dict[str, Any]:
        today = datetime.date.today().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM daily_stats WHERE date = ?", (today,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return {"date": today, "active_seconds": 0.0, "reminders_count": 0, "completed_breaks": 0, "snooze_count": 0, "long_idle_count": 0}

    def update_today_stats(self, active_seconds: float, reminders_count: int, completed_breaks: int, snooze_count: int, long_idle_count: int = 0) -> None:
        today = datetime.date.today().isoformat()
        now_str = datetime.datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO daily_stats (date, active_seconds, reminders_count, completed_breaks, snooze_count, long_idle_count, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    active_seconds = excluded.active_seconds,
                    reminders_count = excluded.reminders_count,
                    completed_breaks = excluded.completed_breaks,
                    snooze_count = excluded.snooze_count,
                    long_idle_count = daily_stats.long_idle_count + excluded.long_idle_count,
                    last_updated = excluded.last_updated
            """, (today, active_seconds, reminders_count, completed_breaks, snooze_count, long_idle_count, now_str))
            conn.commit()
