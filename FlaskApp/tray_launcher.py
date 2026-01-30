"""
AI Spam Detector - Advanced System Tray Application
- Đăng nhập Gmail
- Auto check email realtime
- Popup notification khi phát hiện spam
"""

import sys
import webbrowser
import subprocess
import threading
import time
import signal
from pathlib import Path
from datetime import datetime
import json

try:
    from pystray import Icon, Menu, MenuItem
    from PIL import Image, ImageDraw
    import win32gui
    import win32con
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    print("⚠️  Cài đặt dependencies: pip install pystray pillow pywin32")

# Import services
sys.path.insert(0, str(Path(__file__).parent))
from src.services import EmailService
from src.core import ModelManager

class AdvancedTrayApp:
    def __init__(self):
        self.icon = None
        self.email_service = None
        self.model_manager = None
        self.is_logged_in = False
        self.is_monitoring = False
        self.current_email = None
        self.check_interval = 60  # 60 giây
        self.monitor_thread = None
        self.dashboard_started = False  # Flask chưa start
        self.auto_checker_process = None  # Process cho auto checker
        
    def create_icon_image(self, color='#4F46E5'):
        """Tạo icon với màu tùy chỉnh"""
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), color=color)
        dc = ImageDraw.Draw(image)
        
        # Vẽ shield icon
        dc.ellipse([10, 10, 54, 54], fill='white')
        dc.text((18, 20), "AI", fill=color, font=None)
        
        return image
    
    def show_notification(self, title, message, is_spam=False):
        """Hiển thị Windows notification"""
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            icon_path = None
            
            # Hiển thị notification
            toaster.show_toast(
                title,
                message,
                duration=10,
                threaded=True,
                icon_path=icon_path
            )
        except ImportError:
            # Fallback: sử dụng messagebox
            import ctypes
            MessageBox = ctypes.windll.user32.MessageBoxW
            MessageBox(None, message, title, 0x40 if not is_spam else 0x30)
    
    
    def start_flask(self):
        """Khởi động Flask server trong thread"""
        def run_flask():
            print("🚀 Khởi động Flask server...")
            # Import Flask app
            import sys
            from pathlib import Path
            
            # Add project to path
            project_path = Path(__file__).parent
            if str(project_path) not in sys.path:
                sys.path.insert(0, str(project_path))
            
            # Import and run Flask app
            try:
                from app import app
                print("✅ Flask app imported thành công")
                app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
            except Exception as e:
                print(f"❌ Lỗi khởi động Flask: {e}")
        
        # Chạy Flask trong thread
        print("⏳ Đang khởi động Flask trong thread...")
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        
        # Đợi Flask khởi động
        print("⏳ Đang đợi Flask sẵn sàng...")
        for i in range(15):
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result = sock.connect_ex(('127.0.0.1', 5000))
                sock.close()
                if result == 0:
                    print("✅ Flask đã sẵn sàng!")
                    return
            except:
                pass
            time.sleep(1)
        
        print("⚠️ Flask khởi động chậm, nhưng vẫn tiếp tục...")
    
    
    def login_gmail(self, icon, item):
        """Hiển thị dialog đăng nhập Gmail qua subprocess"""
        try:
            # Chạy dialog trong process riêng để tránh conflict với pystray
            login_script = Path(__file__).parent / "gmail_login_standalone.py"
            
            result = subprocess.run(
                [sys.executable, str(login_script)],
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )
            
            if result.returncode != 0:
                # User hủy hoặc có lỗi
                return
            
            # Parse output: email|||password
            output = result.stdout.strip()
            if not output or '|||' not in output:
                self.show_notification("❌ Lỗi", "Không nhận được thông tin đăng nhập")
                return
            
            email, password = output.split('|||', 1)
            
            # Kết nối Gmail
            self.email_service = EmailService()
            success, msg = self.email_service.connect(email, password)
            
            if success:
                self.is_logged_in = True
                self.current_email = email
                self.model_manager = ModelManager()
                
                # Cập nhật menu
                self.update_menu()
                self.show_notification(
                    "✅ Đăng nhập thành công",
                    f"Đã kết nối: {email}"
                )
            else:
                self.show_notification(
                    "❌ Đăng nhập thất bại",
                    msg,
                    is_spam=True
                )
        except subprocess.TimeoutExpired:
            self.show_notification("⚠️ Timeout", "Dialog đăng nhập quá lâu")
        except Exception as e:
            self.show_notification(
                "❌ Lỗi kết nối",
                str(e),
                is_spam=True
            )
    
    def logout_gmail(self, icon, item):
        """Đăng xuất Gmail"""
        if self.email_service:
            self.stop_monitoring(icon, item)
            self.email_service.disconnect()
        
        self.is_logged_in = False
        self.current_email = None
        self.email_service = None
        
        self.update_menu()
        self.show_notification("🚪 Đã đăng xuất", "Ngắt kết nối Gmail thành công")
    
    def start_monitoring(self, icon, item):
        """Bắt đầu giám sát email"""
        if not self.is_logged_in:
            self.show_notification("⚠️ Chưa đăng nhập", "Vui lòng đăng nhập Gmail trước")
            return
        
        self.is_monitoring = True
        self.monitor_thread = threading.Thread(target=self.monitor_emails, daemon=True)
        self.monitor_thread.start()
        
        self.update_menu()
        self.show_notification(
            "🔍 Bắt đầu giám sát",
            f"Đang quét email mỗi {self.check_interval}s"
        )
    
    def stop_monitoring(self, icon, item):
        """Dừng giám sát email"""
        self.is_monitoring = False
        self.update_menu()
        self.show_notification("⏸️ Dừng giám sát", "Đã tắt auto check email")
    
    def monitor_emails(self):
        """Thread giám sát email liên tục"""
        last_check_time = None
        
        while self.is_monitoring:
            try:
                # Fetch emails mới
                emails, msg = self.email_service.fetch_recent_emails(limit=5)
                
                if emails:
                    spam_count = 0
                    spam_subjects = []
                    
                    for email_data in emails:
                        # Chỉ check email mới (sau lần check trước)
                        email_time = email_data.get('date', '')
                        
                        # Phân tích spam
                        prediction = self.model_manager.predict_single(
                            email_data['full_body'],
                            'Voting Classifier'
                        )
                        
                        if prediction == 'Spam':
                            spam_count += 1
                            spam_subjects.append(email_data['subject'][:50])
                    
                    # Thông báo nếu có spam
                    if spam_count > 0:
                        self.show_notification(
                            f"🚫 Phát hiện {spam_count} email SPAM!",
                            "\n".join(spam_subjects[:3]),
                            is_spam=True
                        )
                        
                        # Đổi màu icon sang đỏ
                        self.icon.icon = self.create_icon_image('#EF4444')
                    else:
                        # Icon xanh nếu không có spam
                        self.icon.icon = self.create_icon_image('#10B981')
                
                last_check_time = datetime.now()
                
            except Exception as e:
                print(f"Monitor error: {e}")
            
            # Đợi trước khi check lần tiếp theo
            time.sleep(self.check_interval)
    
    def check_now(self, icon, item):
        """Check email ngay lập tức"""
        if not self.is_logged_in:
            self.show_notification("⚠️ Chưa đăng nhập", "Vui lòng đăng nhập Gmail trước")
            return
        
        try:
            emails, msg = self.email_service.fetch_recent_emails(limit=10)
            if emails:
                spam_count = sum(
                    1 for e in emails 
                    if self.model_manager.predict_single(e['full_body'], 'Voting Classifier') == 'Spam'
                )
                
                self.show_notification(
                    "📬 Kết quả quét",
                    f"Tổng: {len(emails)} email\nSpam: {spam_count}\nHam: {len(emails) - spam_count}"
                )
        except Exception as e:
            self.show_notification("❌ Lỗi", str(e), is_spam=True)
    
    def open_dashboard(self, icon, item):
        """Mở Dashboard (khởi động Flask nếu chưa)"""
        if not self.dashboard_started:
            print("🚀 Khởi động Dashboard lần đầu...")
            self.start_flask()
            self.dashboard_started = True
        
        print("🌐 Mở Dashboard...")
        webbrowser.open("http://localhost:5000")
    
    def start_auto_checker(self, icon, item):
        """Khởi động Auto Email Checker trong console"""
        if self.auto_checker_process:
            print("⚠️ Auto Checker đã đang chạy rồi!")
            return
        
        print("\n" + "="*70)
        print("🔍 KHỞI ĐỘNG AUTO EMAIL CHECKER")
        print("="*70)
        auto_checker_path = Path(__file__).parent / "auto_checker.py"
        print(f"📂 Script: {auto_checker_path}")
        
        # Chạy auto_checker trong console window riêng
        self.auto_checker_process = subprocess.Popen(
            [sys.executable, str(auto_checker_path)],
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0
        )
        
        print(f"✅ Auto Checker process started! PID: {self.auto_checker_process.pid}")
        print("📌 Console window đã mở - Check taskbar nếu không thấy")
        print("="*70 + "\n")
        
        # Update menu để hiển thị nút "Dừng"
        self.update_menu()
    
    def stop_auto_checker(self, icon, item):
        """Dừng Auto Email Checker"""
        if not self.auto_checker_process:
            print("⚠️ Auto Checker chưa được khởi động")
            return
        
        print("\n🛑 Đang dừng Auto Email Checker...")
        try:
            self.auto_checker_process.terminate()
            self.auto_checker_process.wait(timeout=3)
            self.auto_checker_process = None
            print("✅ Auto Checker đã được dừng\n")
        except:
            self.auto_checker_process.kill()
            self.auto_checker_process = None
            print("✅ Auto Checker đã được dừng (force)\n")
        
        # Update menu
        self.update_menu()
    
    def update_menu(self):
        """Cập nhật menu dựa trên trạng thái"""
        if not self.icon:
            return
        
        # Auto Checker status
        auto_checker_text = "🛑 Dừng Auto Check" if self.auto_checker_process else "▶️ Bắt đầu Auto Check"
        auto_checker_action = self.stop_auto_checker if self.auto_checker_process else self.start_auto_checker
        
        if not self.is_logged_in:
            menu = Menu(
                MenuItem('🌐 Mở Dashboard', self.open_dashboard),
                Menu.SEPARATOR,
                MenuItem(auto_checker_text, auto_checker_action),
                Menu.SEPARATOR,
                MenuItem('🔐 Đăng nhập Gmail', self.login_gmail),
                Menu.SEPARATOR,
                MenuItem('🛑 Thoát', self.quit_app)
            )
        else:
            status = f"✅ {self.current_email}"
            monitor_text = "⏸️ Dừng giám sát" if self.is_monitoring else "▶️ Bắt đầu giám sát"
            monitor_action = self.stop_monitoring if self.is_monitoring else self.start_monitoring
            
            menu = Menu(
                MenuItem(status, None, enabled=False),
                Menu.SEPARATOR,
                MenuItem('🌐 Mở Dashboard', self.open_dashboard),
                MenuItem('🔍 Quét email ngay', self.check_now),
                Menu.SEPARATOR,
                MenuItem(monitor_text, monitor_action),
                MenuItem(auto_checker_text, auto_checker_action),
                Menu.SEPARATOR,
                MenuItem('🚪 Đăng xuất', self.logout_gmail),
                MenuItem('🛑 Thoát', self.quit_app)
            )
        
        self.icon.menu = menu
    
    def quit_app(self, icon, item):
        """Thoát ứng dụng"""
        print("🛑 Đang tắt ứng dụng...")
        
        # Dừng monitoring
        self.is_monitoring = False
        
        # Ngắt kết nối email
        if self.email_service:
            try:
                self.email_service.disconnect()
            except:
                pass
        
        # Dừng auto checker nếu đang chạy
        if self.auto_checker_process:
            try:
                self.auto_checker_process.terminate()
                self.auto_checker_process.wait(timeout=2)
            except:
                self.auto_checker_process.kill()
        
        # Dừng icon
        icon.stop()
        
        # Force exit (Flask thread sẽ tự tắt vì là daemon)
        import os
        os._exit(0)
    
    def run(self):
        """Chạy ứng dụng"""
        if not TRAY_AVAILABLE:
            print("❌ Thiếu dependencies. Chạy: pip install pystray pillow pywin32 win10toast")
            return
        
        # Setup signal handlers
        def signal_handler(sig, frame):
            print("\n🛑 Đang tắt ứng dụng...")
            if self.icon:
                self.icon.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Không auto-start Flask, chỉ start khi người dùng click "Dashboard"
        print("📌 Flask sẽ khởi động khi bạn mở Dashboard lần đầu")
        
        # Tạo system tray icon
        self.icon = Icon(
            "AI Spam Detector",
            self.create_icon_image(),
            "AI Spam Detector"
        )
        
        # Khởi tạo menu
        self.update_menu()
        
        print("✅ AI Spam Detector đang chạy trên system tray")
        print("📌 Click phải icon trên system tray để sử dụng menu")
        print("🌐 Chọn 'Mở Dashboard' để khởi động giao diện web")
        print("🔍 Chọn 'Bắt đầu Auto Check' để tự động kiểm tra email")
        
        try:
            self.icon.run()
        except KeyboardInterrupt:
            pass

if __name__ == "__main__":
    try:
        app = AdvancedTrayApp()
        app.run()
    except KeyboardInterrupt:
        print("\n🛑 Đang tắt ứng dụng...")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Lỗi: {e}")
        sys.exit(1)
