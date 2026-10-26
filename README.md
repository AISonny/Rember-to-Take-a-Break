# Windows 11 電腦使用時間與健康休息提醒工具

專為 Windows 11 打造的個人健康休息提醒工具，透過實體輸入活動判定、三段式閒置容錯與 11 種狀態機，在每滿 45 分鐘時以 Windows 11 Toast 系統通知與現代桌面彈窗提醒伸展與喝水。

## 快速開始
```bash
pip install -r requirements.txt
python main.py
```

## 執行 20 項單元測試
```bash
python -m unittest tests/test_timer.py -v
```

## 打包獨立執行檔
```bash
python build_exe.py
```
