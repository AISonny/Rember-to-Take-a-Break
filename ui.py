"""
Windows 11 電腦使用時間與健康休息提醒工具
UI: PySide6 桌面主視窗、休息提醒彈窗、設定頁面與歷史紀錄對話框
"""

from __future__ import annotations
import sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QDialog, QFormLayout, QSpinBox, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QFrame,
)
from timer_engine import TimerEngine, AppState, TimerConfig
from storage import SettingsStorage, HistoryStorage
from autostart import is_autostart_enabled, set_autostart

def format_seconds(seconds: float) -> str:
    total_sec = int(max(0, seconds))
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

STATE_LABELS = {
    AppState.ACTIVE: ("累積活動中", "#10B981"),
    AppState.SHORT_IDLE: ("短暫閒置 (容錯保留)", "#3B82F6"),
    AppState.INACTIVE: ("暫停累積 (一般閒置)", "#F59E0B"),
    AppState.LONG_IDLE: ("長時間閒置 (已記錄)", "#EF4444"),
    AppState.BREAK_DUE: ("已達 45 分鐘！請休息", "#8B5CF6"),
    AppState.BREAK_PAUSED: ("休息中 (進度保留)", "#06B6D4"),
    AppState.PAUSED: ("手動暫停中", "#6B7280"),
    AppState.LOCKED: ("Windows 已鎖定", "#64748B"),
    AppState.SUSPENDED: ("系統睡眠中", "#64748B"),
    AppState.RESUMING: ("系統恢復中", "#3B82F6"),
    AppState.STOPPED: ("已停止", "#475569"),
}

class BreakDialog(QDialog):
    """45 分鐘健康休息桌面彈出視窗"""
    def __init__(self, engine: TimerEngine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.setWindowTitle("健康休息提醒 - 照顧自己的身體")
        self.setFixedSize(460, 360)
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title_label = QLabel("🌿 該起身休息一下了！")
        title_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        active_str = format_seconds(self.engine.cycle_active_seconds)
        desc_label = QLabel(
            f"您已連續累積 <b>{active_str}</b> 的實際電腦活動時間。<br><br>"
            "長時間維持相同姿勢會對肩頸、眼睛及腰椎造成負擔。<br>"
            "請起身走動 3~5 分鐘、向遠處眺望、做做深呼吸並喝一杯水。"
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #334155; font-size: 14px; line-height: 1.5;")
        layout.addWidget(desc_label)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #E2E8F0;")
        layout.addWidget(line)

        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(8)

        btn_completed = QPushButton("✓ 我已完成健康休息（開始新一輪）")
        btn_completed.setStyleSheet("background-color: #10B981; color: white; padding: 10px; font-weight: bold; border-radius: 6px;")
        btn_completed.clicked.connect(self.on_completed)
        btn_layout.addWidget(btn_completed)

        h_btn_box = QHBoxLayout()
        btn_snooze = QPushButton("⏰ 稍後 5 分鐘提醒")
        btn_snooze.clicked.connect(self.on_snooze)
        h_btn_box.addWidget(btn_snooze)

        btn_resting = QPushButton("🍵 我正在休息中")
        btn_resting.clicked.connect(self.on_resting)
        h_btn_box.addWidget(btn_resting)
        btn_layout.addLayout(h_btn_box)

        h_btn_box2 = QHBoxLayout()
        btn_pause = QPushButton("⏸ 暫停提醒")
        btn_pause.clicked.connect(self.on_pause)
        h_btn_box2.addWidget(btn_pause)

        btn_close = QPushButton("✕ 僅關閉視窗 (保留待處理)")
        btn_close.clicked.connect(self.on_close_only)
        h_btn_box2.addWidget(btn_close)
        btn_layout.addLayout(h_btn_box2)

        layout.addLayout(btn_layout)

    def on_completed(self):
        self.engine.action_break_completed()
        self.accept()

    def on_snooze(self):
        self.engine.action_snooze()
        self.accept()

    def on_resting(self):
        self.engine.action_resting_now()
        self.accept()

    def on_pause(self):
        self.engine.action_pause_reminder()
        self.accept()

    def on_close_only(self):
        self.engine.action_dismiss_window_only()
        self.reject()

class MainWindow(QMainWindow):
    """主視窗 (符合規格第七節全部 12 項要求)"""
    def __init__(self, engine: TimerEngine, settings: SettingsStorage, history: HistoryStorage):
        super().__init__()
        self.engine = engine
        self.settings = settings
        self.history = history
        self.setWindowTitle("Windows 11 健康休息提醒工具")
        self.setFixedSize(480, 560)
        self.init_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_display)
        self.timer.start(1000)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(14)

        header_box = QHBoxLayout()
        title_label = QLabel("💻 電腦使用健康提醒")
        title_label.setFont(QFont("Segoe UI", 15, QFont.Bold))
        self.lbl_status = QLabel("累積活動中")
        header_box.addWidget(title_label)
        header_box.addStretch()
        header_box.addWidget(self.lbl_status)
        main_layout.addLayout(header_box)

        card_widget = QFrame()
        card_widget.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px;")
        card_layout = QVBoxLayout(card_widget)
        self.lbl_cycle_time = QLabel("00:00:00")
        self.lbl_cycle_time.setFont(QFont("Segoe UI", 28, QFont.Bold))
        self.lbl_rem_time = QLabel("45:00")
        card_layout.addWidget(QLabel("本輪有效電腦活動時間"))
        card_layout.addWidget(self.lbl_cycle_time)
        card_layout.addWidget(self.lbl_rem_time)
        main_layout.addWidget(card_widget)

        self.btn_toggle_pause = QPushButton("⏸ 暫停計時")
        self.btn_toggle_pause.clicked.connect(self.toggle_pause)
        main_layout.addWidget(self.btn_toggle_pause)

    def update_display(self):
        curr_state = self.engine.state
        state_text, state_color = STATE_LABELS.get(curr_state, ("未知", "#6B7280"))
        self.lbl_status.setText(state_text)
        self.lbl_status.setStyleSheet(f"background-color: {state_color}; color: white; padding: 4px 10px; border-radius: 12px;")
        self.lbl_cycle_time.setText(format_seconds(self.engine.cycle_active_seconds))
        self.lbl_rem_time.setText(f"距離下次提醒: {format_seconds(self.engine.remaining_seconds_to_break)}")

    def toggle_pause(self):
        if self.engine.state == AppState.PAUSED:
            self.engine.action_resume()
        else:
            self.engine.action_pause_reminder()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
