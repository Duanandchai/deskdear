# -*- coding: utf-8 -*-
"""Windows 开机自启管理：通过当前用户注册表 Run 键实现，无需管理员权限。"""
import os
import sys
import winreg

APP_NAME = "DeskDear"
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _launch_command() -> str:
    """生成开机启动命令。

    打包后直接启动 exe；源码运行时通过 pythonw.exe 静默启动 main.py。
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    launcher = pythonw if os.path.exists(pythonw) else sys.executable
    script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))
    return f'"{launcher}" "{script}"'


def is_enabled() -> bool:
    """查询注册表中是否已注册开机自启。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    """写入或删除开机自启项。失败时抛出 OSError，由调用方处理提示。"""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
