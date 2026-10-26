"""
Windows 11 電腦使用時間與健康休息提醒工具
PyInstaller 打包建置腳本 (產出 dist/Win11HealthBreakReminder.exe)
"""
import os
import sys
import subprocess

def build():
    print("開始建置 Windows 11 獨立可執行檔 (.exe)...")
    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        "--name=Win11HealthBreakReminder",
        "--clean",
        "--hidden-import=PySide6.QtCore",
        "--hidden-import=PySide6.QtGui",
        "--hidden-import=PySide6.QtWidgets",
        "--hidden-import=windows_toasts",
        "main.py",
    ]
    res = subprocess.run(cmd)
    if res.returncode == 0:
        print("打包成功！檔案位於 dist/Win11HealthBreakReminder.exe")

if __name__ == "__main__":
    build()
