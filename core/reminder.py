# -*- coding: utf-8 -*-
"""【预留扩展】定时提醒管理器。

当前实现：按固定间隔通过系统托盘气泡提醒喝水、休息。
后续可扩展为：多条提醒计划、自定义文案、弹窗提醒、与聊天模块联动等。
配置项：reminder_enabled / reminder_interval_minutes。
"""
from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QSystemTrayIcon


class ReminderManager(QObject):
    """基于托盘气泡的轻量定时提醒（无多余弹窗）。"""

    # 预留：提醒文案池，可随机选取
    MESSAGES = [
        "主人，工作好久啦，记得喝点水哦~",
        "主人，休息一下眼睛吧，看看远处~",
        "主人，起来活动一下身体嘛~",
    ]

    def __init__(self, pet_window, parent=None):
        super().__init__(parent or pet_window)
        self._pet = pet_window
        self._index = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._notify)

    # ---------------- 控制接口 ----------------
    def set_enabled(self, enabled: bool) -> None:
        """开启或关闭定时提醒，间隔从配置读取（分钟）。"""
        self._timer.stop()
        if enabled:
            minutes = max(1, self._pet.cfg.get_int("reminder_interval_minutes") or 45)
            self._timer.start(minutes * 60 * 1000)

    def is_enabled(self) -> bool:
        return self._timer.isActive()

    # ---------------- 提醒逻辑 ----------------
    def _notify(self) -> None:
        text = self.MESSAGES[self._index % len(self.MESSAGES)]
        self._index += 1
        self._pet.tray.showMessage(
            "DeskDear 贴心提醒",
            text,
            QSystemTrayIcon.Information,
            6000,
        )
