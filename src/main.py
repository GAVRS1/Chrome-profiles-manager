import sys
import ctypes
from PySide6.QtWidgets import QApplication
from app.gui import MainWindow

def _require_admin():
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        is_admin = False
    if not is_admin:
        # Предупреждение только в консоль; запуск возможен, но функциональность может быть ограничена
        print("[WARN] Запустите от имени администратора для глобальных хуков и отправки ввода.")

if __name__ == "__main__":
    _require_admin()
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
