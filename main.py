# -*- coding: utf-8 -*-
"""DeskDear —— Windows 桌面 AI 助手

启动入口：
    python main.py

打包后：
    直接双击 dist/DeskDear.exe
"""
import sys

from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from core.config_manager import ConfigManager
from core.pet_window import PetWindow


def main() -> int:
    QApplication.setApplicationName("DeskDear")
    QApplication.setOrganizationName("DeskDear")
    app = QApplication(sys.argv)
    # 关闭聊天气泡 / 设置窗口时不退出程序（桌宠常驻托盘）
    app.setQuitOnLastWindowClosed(False)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "DeskDear", "当前系统不支持系统托盘，程序无法运行。")
        return 1

    cfg = ConfigManager()
    pet = PetWindow(cfg)
    pet.show()

    # 应用图标与托盘图标保持一致
    app.setWindowIcon(pet.tray.icon())

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
