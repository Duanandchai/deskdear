# -*- coding: utf-8 -*-
"""资源路径工具：兼容源码运行与 PyInstaller 打包后的路径解析。"""
import os
import sys


def is_frozen() -> bool:
    """是否为 PyInstaller 打包后的可执行文件。"""
    return getattr(sys, "frozen", False)


def app_dir() -> str:
    """应用根目录（打包后为 exe 所在目录，用于存放用户配置）。"""
    if is_frozen():
        return os.path.dirname(sys.executable)
    # core/ 的上一级即项目根目录
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(relative: str) -> str:
    """解析只读资源路径。

    打包后资源被解压到 sys._MEIPASS 临时目录；
    源码运行时相对于项目根目录。
    """
    base = getattr(sys, "_MEIPASS", app_dir())
    return os.path.join(base, relative)


def resolve_skin_root(skin_value: str) -> str:
    """解析皮肤根目录。

    支持两种形式：
    1. 绝对路径（用户在设置面板中自定义的皮肤文件夹）；
    2. 相对路径（相对于内置资源目录，如 assets/skin/girlfriend）。
    """
    if os.path.isabs(skin_value) and os.path.isdir(skin_value):
        return skin_value
    return resource_path(skin_value)


def natural_key(name: str):
    """自然排序键：让 'xx2.png' 排在 'xx10.png' 之前。"""
    import re

    parts = re.split(r"(\d+)", name)
    return [int(p) if p.isdigit() else p.lower() for p in parts]
