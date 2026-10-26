"""
Windows 11 電腦使用時間與健康休息提醒工具
Tray: Windows 11 系統匣圖示與常駐功能模組
"""

from __future__ import annotations
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtCore import Qt
from timer_engine import TimerEngine, AppState

def create_default_tray_pixmap() -> QPixmap:
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(37, 99, 235))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(2, 2, 28, 28)
    painter.setBrush(QColor(255, 255, 255))
    painter.drawEllipse(7, 7, 18, 18)
    painter.setBrush(QColor(16, 185, 129))
    painter.drawEllipse(13, 13, 6, 6)
    painter.end()
    return pixmap

class SystemTrayManager:
    def __init__(self, main_window, engine: TimerEngine):
        self.main_window = main_window
        self.engine = engine
        self.tray_icon = QSystemTrayIcon()
        self.tray_icon.setIcon(QIcon(create_default_tray_pixmap()))
        self.tray_icon.setToolTip("Windows 11 健康休息提醒工具")
        self.init_menu()
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def init_menu(self):
        menu = QMenu()
        act_open = menu.addAction("🖥 開啟主畫面")
        act_open.triggered.connect(self.show_main_window)
        self.act_pause = menu.addAction("⏸ 暫停提醒")
        self.act_pause.triggered.connect(self.toggle_pause)
        act_phone = menu.addAction("📱 標記短暫使用手機")
        act_phone.triggered.connect(self.engine.manual_mark_phone_use)
        menu.addSeparator()
        act_exit = menu.addAction("✕ 結束程式")
        act_exit.triggered.connect(self.exit_app)
        self.tray_icon.setContextMenu(menu)

    def show_main_window(self):
        self.main_window.showNormal()
        self.main_window.activateWindow()

    def toggle_pause(self):
        if self.engine.state == AppState.PAUSED:
            self.engine.action_resume()
            self.act_pause.setText("⏸ 暫停提醒")
        else:
            self.engine.action_pause_reminder()
            self.act_pause.setText("▶ 恢復計時")

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_main_window()

    def exit_app(self):
        self.engine.stop()
        QApplication.quit()
