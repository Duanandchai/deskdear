# -*- coding: utf-8 -*-
"""【预留扩展】桌面随机漫游控制器。

后续可在此基础上扩展：自动在桌面缓慢移动、碰到屏幕边界转向、
随机上下浮动等。当前实现为最小可用的水平漫游版本，默认关闭，
可通过右键菜单或配置文件 roam_enabled 开启。
"""
import random

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication


class RoamController(QObject):
    """让桌宠在屏幕上缓慢水平移动，碰到边界自动转向。"""

    def __init__(self, pet_window, parent=None):
        super().__init__(parent or pet_window)
        self._pet = pet_window
        self._dx = random.choice([-2, -1, 1, 2])  # 每 tick 水平位移（像素）
        self._steps = 0

        self._timer = QTimer(self)
        self._timer.setInterval(50)  # 20fps 的移动刷新，足够平滑且低占用
        self._timer.timeout.connect(self._tick)

    # ---------------- 控制接口 ----------------
    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def is_running(self) -> bool:
        return self._timer.isActive()

    # ---------------- 移动逻辑 ----------------
    def _tick(self) -> None:
        pet = self._pet
        # 角色隐藏或正在被拖拽时暂停漫游
        if not pet.isVisible() or pet.is_dragging:
            return

        screen = QApplication.screenAt(pet.geometry().center()) or QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()

        next_x = pet.x() + self._dx
        # 碰到屏幕左右边界：转向
        if next_x <= avail.left() or next_x + pet.width() >= avail.right():
            self._dx = -self._dx
            next_x = pet.x() + self._dx
        pet.move(next_x, pet.y())

        # 每隔一段时间随机换向，让漫游更自然
        self._steps += 1
        if self._steps % 600 == 0 and random.random() < 0.4:
            self._dx = -self._dx
