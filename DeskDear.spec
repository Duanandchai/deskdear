# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：单文件、无控制台窗口、内置 assets 素材。

用法：
    pyinstaller --noconfirm --clean DeskDear.spec
产物：
    dist/DeskDear.exe
"""
import os

# 若存在 assets/icon.ico 则作为 exe 图标（可选）
ICON_FILE = "assets/icon.ico" if os.path.exists("assets/icon.ico") else None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("assets", "assets")],  # 素材目录整体打进 exe，运行时解压到 _MEIPASS
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc"],  # 裁剪无用模块，减小体积
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="DeskDear",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,             # 环境中有 UPX 时可改为 True 进一步压缩体积
    console=False,         # 无控制台黑窗口
    disable_windowed_traceback=False,
    icon=ICON_FILE,
)
