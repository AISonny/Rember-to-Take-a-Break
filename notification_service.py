"""
Windows 11 電腦使用時間與健康休息提醒工具
Notification Service: Windows 11 原生通知與提示音效模組
"""

from __future__ import annotations
import sys
import subprocess
import threading

class NotificationService:
    def __init__(self, enable_sound: bool = True):
        self.enable_sound = enable_sound
        self._is_windows = sys.platform.startswith("win")

    def send_break_notification(
        self,
        title: str = "休息一下，照顧自己的健康",
        message: str = "你已累積 45 分鐘的有效電腦活動時間。請起身走動、伸展肩頸，並補充水分。",
    ) -> None:
        threading.Thread(target=self._send_sync, args=(title, message), daemon=True).start()

    def _send_sync(self, title: str, message: str) -> None:
        if self.enable_sound and self._is_windows:
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass

        if not self._is_windows:
            print(f"[系統通知模擬] {title} - {message}")
            return

        try:
            from windows_toasts import Toast, WindowsToaster
            toaster = WindowsToaster("健康休息提醒")
            new_toast = Toast()
            new_toast.text_fields = [title, message]
            toaster.show_toast(new_toast)
            return
        except ImportError:
            pass
        except Exception as e:
            print(f"[Notification] windows-toasts 備援觸發: {e}")

        try:
            ps_script = f"""
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
            $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
            $textNodes = $template.GetElementsByTagName("text")
            $textNodes.Item(0).AppendChild($template.CreateTextNode('{title}')) > $null
            $textNodes.Item(1).AppendChild($template.CreateTextNode('{message}')) > $null
            $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('健康休息提醒工具')
            $notification = [Windows.UI.Notifications.ToastNotification]::new($template)
            $notifier.Show($notification)
            """
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                capture_output=True,
                creationflags=0x08000000 if self._is_windows else 0,
                timeout=5,
            )
        except Exception as e:
            print(f"[Notification] 系統通知發送失敗: {e}")
