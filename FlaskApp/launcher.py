"""
AI Spam Detector - Windows Launcher
Chạy Flask app và mở browser tự động
"""

import sys
import webbrowser
import time
import subprocess
from pathlib import Path
import threading

def start_flask_server():
    """Khởi động Flask server"""
    print("🚀 Đang khởi động AI Spam Detector...")
    
    # Chạy Flask app
    app_path = Path(__file__).parent / "app.py"
    process = subprocess.Popen(
        [sys.executable, str(app_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Đợi server khởi động
    time.sleep(3)
    
    # Mở browser
    print("🌐 Đang mở trình duyệt...")
    webbrowser.open("http://localhost:5000")
    
    print("\n" + "="*70)
    print("✅ AI Spam Detector đã sẵn sàng!")
    print("🌐 Truy cập: http://localhost:5000")
    print("⚠️  Đóng cửa sổ này để tắt ứng dụng")
    print("="*70 + "\n")
    
    # Giữ process chạy
    try:
        process.wait()
    except KeyboardInterrupt:
        print("\n🛑 Đang tắt ứng dụng...")
        process.terminate()

if __name__ == "__main__":
    start_flask_server()
