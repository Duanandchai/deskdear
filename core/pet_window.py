# -*- coding: utf-8 -*-
"""桌宠主窗口：无边框透明窗口 + 状态机调度 + 右键菜单 + 系统托盘。

实现的功能要点：
- 无边框透明窗口（FramelessWindowHint + WA_TranslucentBackground，Win10/11 稳定方案）；
- 始终置顶、左键拖拽移动（带屏幕边界检测）、滚轮缩放、鼠标穿透开关；
- 右键菜单：显示/隐藏、调整尺寸、互动动画、开机自启、设置面板、退出；
- 系统托盘驻留：双击托盘图标显示/隐藏角色；
- 闲置倒计时：无交互 60 秒进入委屈、90 秒进入犯困（秒数可在设置中修改）；
- 状态机硬性流转规则见各事件处理函数注释。
"""
import random

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QStyle, QSystemTrayIcon, QWidget

from core import autostart
from core.animation import AnimationPlayer, PetState
from core.chat_bubble import ChatBubble
from core.reminder import ReminderManager
from core.resource_utils import resolve_skin_root
from core.roam import RoamController
from core.settings_dialog import SettingsDialog

MIN_SCALE, MAX_SCALE = 0.1, 3.0
SCALE_STEP = 0.1

# 发呆（daze）随机触发区间（秒），仅作为状态展示用途
DAZE_INTERVAL_RANGE = (120, 300)   # 每隔 2~5 分钟随机发呆一次
DAZE_DURATION_RANGE = (15, 25)     # 发呆持续 15~25 秒后自动回到待机


class PetWindow(QWidget):
    """桌宠角色窗口。"""

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg

        # ---- 拖拽状态标记 ----
        self._maybe_drag = False   # 左键已按下，等待判定是点击还是拖拽
        self._dragging = False     # 已确认进入拖拽
        self._press_global = QPoint()
        self._drag_offset = QPoint()
        self._positioned = False   # 首帧显示前是否已完成初始定位

        # ---- 窗口外观 ----
        self.setWindowFlags(self._build_window_flags())
        self.setAttribute(Qt.WA_TranslucentBackground)  # 透明背景
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)

        # ---- 动画播放器（状态机核心）----
        self.player = AnimationPlayer(
            resolve_skin_root(cfg.get_str("skin_path") or "assets/skin/girlfriend"),
            scale=cfg.get_float("scale") or 0.25,
            speed=cfg.get_float("animation_speed") or 1.0,
            parent=self,
        )
        self.player.frame_changed.connect(self._on_frame_changed)
        self.player.one_shot_finished.connect(self._on_one_shot_finished)

        # ---- 闲置倒计时定时器 ----
        self.timer_sad = QTimer(self)
        self.timer_sad.setSingleShot(True)
        self.timer_sad.timeout.connect(self._enter_sad)
        self.timer_sleepy = QTimer(self)
        self.timer_sleepy.setSingleShot(True)
        self.timer_sleepy.timeout.connect(self._enter_sleepy)

        # ---- 发呆随机触发定时器 ----
        self.timer_daze = QTimer(self)
        self.timer_daze.setSingleShot(True)
        self.timer_daze.timeout.connect(self._maybe_enter_daze)
        self.timer_daze_back = QTimer(self)
        self.timer_daze_back.setSingleShot(True)
        self.timer_daze_back.timeout.connect(self._leave_daze)

        # ---- 系统托盘 / 聊天气泡 / 预留功能 ----
        self._build_tray()
        self.chat_bubble = ChatBubble(cfg, pet=self)
        self.roam = RoamController(self)
        self.reminder = ReminderManager(self)

        # ---- 应用初始配置 ----
        self._apply_passthrough(cfg.get_bool("mouse_passthrough"))
        if cfg.get_bool("roam_enabled"):
            self.roam.start()
        self.reminder.set_enabled(cfg.get_bool("reminder_enabled"))

        # ---- 启动：进入待机，启动计时器，稍后挥手打招呼 ----
        self.player.play(PetState.IDLE)
        self.reset_idle_timers()
        self._schedule_daze()
        QTimer.singleShot(600, self._greet)

    # ================== 属性 ==================
    @property
    def is_dragging(self) -> bool:
        return self._dragging

    # ================== 窗口标志与外观 ==================
    def _build_window_flags(self) -> Qt.WindowFlags:
        flags = Qt.FramelessWindowHint | Qt.Tool  # Tool：不在任务栏显示图标
        if self.cfg.get_bool("always_on_top"):
            flags |= Qt.WindowStaysOnTopHint
        return flags

    def _apply_window_flags(self) -> None:
        """修改窗口标志（置顶开关）后需要重新 show 才生效。"""
        was_visible = self.isVisible()
        self.setWindowFlags(self._build_window_flags())
        if was_visible:
            self.show()

    def _apply_passthrough(self, enabled: bool) -> None:
        """鼠标穿透：使用 Qt 稳定属性实现，不依赖废弃系统 API。"""
        self.setAttribute(Qt.WA_TransparentForMouseEvents, enabled)

    # ================== 动画帧刷新 ==================
    def _on_frame_changed(self, pixmap: QPixmap) -> None:
        """显示当前帧；窗口尺寸跟随帧尺寸，保持角色“脚下”位置不动。"""
        self.label.setPixmap(pixmap)
        if pixmap.size() != self.size():
            old_geometry = self.geometry()
            center_x = old_geometry.center().x()
            bottom = old_geometry.bottom()
            self.resize(pixmap.size())
            self.label.resize(pixmap.size())
            if self._positioned:
                self.move(center_x - pixmap.width() // 2, bottom - pixmap.height())
            self.clamp_to_screen()
        if not self._positioned:
            self._move_to_initial_position()
            self._positioned = True

    def _move_to_initial_position(self) -> None:
        """首次显示：放在主屏幕右下角、任务栏上方。"""
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            self.move(avail.right() - self.width() - 60, avail.bottom() - self.height() - 20)

    def _on_one_shot_finished(self, _state: str) -> None:
        """一次性动画（害羞/跳跃/挥手）播放完毕 → 强制回归待机。"""
        self.player.play(PetState.IDLE)

    # ================== 闲置倒计时 ==================
    def register_interaction(self) -> None:
        """任意用户交互（点击/拖拽/滚轮/聊天）都会重置闲置计时。"""
        self.reset_idle_timers()

    def reset_idle_timers(self) -> None:
        sad_seconds = max(10, self.cfg.get_int("idle_to_sad_seconds") or 60)
        sleepy_seconds = max(sad_seconds, self.cfg.get_int("idle_to_sleepy_seconds") or 90)
        self.timer_sad.start(sad_seconds * 1000)
        self.timer_sleepy.start(sleepy_seconds * 1000)

    def _enter_sad(self) -> None:
        """无交互超时：idle/daze → sad（循环动画即时切换）。"""
        if self._dragging:
            return
        if self.player.current_state in (PetState.IDLE, PetState.DAZE):
            self.player.play(PetState.SAD)

    def _enter_sleepy(self) -> None:
        """持续无交互：idle/sad/daze → sleepy（循环动画即时切换）。"""
        if self._dragging:
            return
        if self.player.current_state in (PetState.IDLE, PetState.SAD, PetState.DAZE):
            self.player.play(PetState.SLEEPY)

    # ================== 发呆（随机点缀状态） ==================
    def _schedule_daze(self) -> None:
        self.timer_daze.start(random.randint(*DAZE_INTERVAL_RANGE) * 1000)

    def _maybe_enter_daze(self) -> None:
        """仅在待机状态下偶尔进入发呆，避免打断委屈/犯困。"""
        if self.player.current_state == PetState.IDLE and not self._dragging:
            self.player.play(PetState.DAZE)
            self.timer_daze_back.start(random.randint(*DAZE_DURATION_RANGE) * 1000)
        self._schedule_daze()

    def _leave_daze(self) -> None:
        if self.player.current_state == PetState.DAZE:
            self.player.play(PetState.IDLE)

    def _greet(self) -> None:
        """启动后挥手打招呼（一次性动画，播完自动回待机）。"""
        if self.player.current_state == PetState.IDLE:
            self.player.play(PetState.WAVE)

    # ================== 鼠标交互 ==================
    def mousePressEvent(self, event) -> None:
        self.register_interaction()
        if event.button() == Qt.LeftButton:
            self._maybe_drag = True
            self._dragging = False
            self._press_global = event.globalPosition().toPoint()
            self._drag_offset = self._press_global - self.frameGeometry().topLeft()
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event) -> None:
        if not (self._maybe_drag and event.buttons() & Qt.LeftButton):
            return
        if not self._dragging:
            # 超过系统拖拽阈值才判定为“拖拽”，否则视为“单击”
            distance = (event.globalPosition().toPoint() - self._press_global).manhattanLength()
            if distance >= QApplication.startDragDistance():
                self._dragging = True
                self.player.play(PetState.DRAG)  # 立刻切换被拖拽静态图
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            self.clamp_to_screen()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or not self._maybe_drag:
            return
        self._maybe_drag = False
        if self._dragging:
            # 松开鼠标：拖拽结束，立即返回待机
            self._dragging = False
            self.player.play(PetState.IDLE)
        else:
            # 单击：立刻中断当前动画，播放害羞，播完自动回待机
            self.player.play(PetState.TOUCH_SHY)

    def mouseDoubleClickEvent(self, event) -> None:
        """双击：开心跳跃（一次性动画，可打断当前任何状态）。"""
        if event.button() == Qt.LeftButton:
            self.register_interaction()
            self.player.play(PetState.HAPPY_JUMP)

    def wheelEvent(self, event) -> None:
        """滚轮缩放角色大小；同时视为一次交互（唤醒委屈/犯困）。"""
        self.register_interaction()
        step = SCALE_STEP if event.angleDelta().y() > 0 else -SCALE_STEP
        self.set_scale((self.cfg.get_float("scale") or 1.0) + step)
        if self.player.current_state in (PetState.SAD, PetState.SLEEPY, PetState.DAZE):
            self.player.play(PetState.IDLE)

    # ================== 屏幕边界检测 ==================
    def clamp_to_screen(self) -> None:
        """保证窗口完整处于屏幕可用区域内，防止角色被拖丢。"""
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        max_x = avail.right() - self.width() + 1
        max_y = avail.bottom() - self.height() + 1
        if max_x < avail.left() or max_y < avail.top():
            return  # 极端情况：窗口比屏幕还大，不处理
        x = min(max(self.x(), avail.left()), max_x)
        y = min(max(self.y(), avail.top()), max_y)
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)

    # ================== 缩放 ==================
    def set_scale(self, value: float) -> None:
        value = round(min(MAX_SCALE, max(MIN_SCALE, value)), 2)
        if abs(value - (self.cfg.get_float("scale") or 1.0)) < 1e-6:
            return
        self.cfg.set("scale", value)
        self.cfg.save()
        self.player.set_scale(value)

    # ================== 右键菜单 ==================
    def _show_context_menu(self, global_pos) -> None:
        menu = QMenu(self)

        # 显示 / 隐藏
        self._add_action(
            menu,
            "隐藏角色" if self.isVisible() else "显示角色",
            self.toggle_visible,
        )
        self._add_action(menu, "打开聊天", self.toggle_chat)

        # 调整尺寸子菜单
        size_menu = menu.addMenu("调整尺寸")
        current_scale = self.cfg.get_float("scale") or 0.25
        for label, value in (
            ("25%", 0.25), ("50%", 0.5), ("75%", 0.75), ("100%", 1.0),
            ("125%", 1.25), ("150%", 1.5), ("200%", 2.0),
        ):
            self._add_action(
                size_menu, label,
                lambda checked=False, v=value: self.set_scale(v),
                checkable=True, checked=abs(current_scale - value) < 0.01,
            )

        # 互动子菜单（演示各一次性 / 循环状态）
        interact_menu = menu.addMenu("互动")
        self._add_action(interact_menu, "挥手打招呼", lambda: self._play_interaction(PetState.WAVE))
        self._add_action(interact_menu, "开心跳跃", lambda: self._play_interaction(PetState.HAPPY_JUMP))
        self._add_action(interact_menu, "发呆思考", lambda: self._play_interaction(PetState.DAZE))

        menu.addSeparator()

        # 开关系列
        self._add_action(
            menu, "始终置顶",
            lambda checked: self._toggle_topmost(checked),
            checkable=True, checked=self.cfg.get_bool("always_on_top"),
        )
        self._add_action(
            menu, "鼠标穿透（开启后请用托盘恢复）",
            lambda checked: self._toggle_passthrough(checked),
            checkable=True, checked=self.cfg.get_bool("mouse_passthrough"),
        )
        self._add_action(
            menu, "桌面漫游（实验）",
            lambda checked: self._toggle_roam(checked),
            checkable=True, checked=self.cfg.get_bool("roam_enabled"),
        )
        self._add_action(
            menu, "定时喝水提醒",
            lambda checked: self._toggle_reminder(checked),
            checkable=True, checked=self.cfg.get_bool("reminder_enabled"),
        )
        self._add_action(
            menu, "开机自启",
            lambda checked: self._toggle_autostart(checked),
            checkable=True, checked=autostart.is_enabled(),
        )

        menu.addSeparator()
        self._add_action(menu, "设置面板", self.open_settings)
        self._add_action(menu, "退出程序", self.quit_app)

        menu.exec(global_pos)

    def _add_action(self, menu, text, handler, checkable=False, checked=False) -> QAction:
        action = QAction(text, self)
        action.setCheckable(checkable)
        if checkable:
            action.setChecked(checked)
        action.triggered.connect(handler)
        menu.addAction(action)
        return action

    def _play_interaction(self, state: str) -> None:
        self.register_interaction()
        self.player.play(state)
        if state == PetState.DAZE:
            # 菜单手动触发的发呆也需在若干秒后回到待机
            self.timer_daze_back.start(random.randint(*DAZE_DURATION_RANGE) * 1000)

    # ================== 菜单动作 ==================
    def toggle_visible(self) -> None:
        self.setVisible(not self.isVisible())

    def toggle_chat(self) -> None:
        if self.chat_bubble.isVisible():
            self.chat_bubble.hide()
        else:
            if not self.isVisible():
                self.setVisible(True)
            self.chat_bubble.show_near(self.geometry())

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.cfg, self)
        dialog.applied.connect(self.apply_settings)
        dialog.exec()

    def apply_settings(self) -> None:
        """设置面板保存后统一应用全部配置。"""
        self._apply_window_flags()
        self._apply_passthrough(self.cfg.get_bool("mouse_passthrough"))
        self.player.set_speed(self.cfg.get_float("animation_speed") or 1.0)

        new_skin = resolve_skin_root(self.cfg.get_str("skin_path") or "assets/skin/girlfriend")
        if new_skin != self.player.skin_root:
            self.player.set_skin_root(new_skin)
            self.tray.setIcon(self._make_tray_icon())

        self.player.set_scale(self.cfg.get_float("scale") or 1.0)
        self.reset_idle_timers()

        if self.cfg.get_bool("roam_enabled"):
            self.roam.start()
        else:
            self.roam.stop()
        self.reminder.set_enabled(self.cfg.get_bool("reminder_enabled"))

    def _toggle_topmost(self, checked: bool) -> None:
        self.cfg.set("always_on_top", checked)
        self.cfg.save()
        self._apply_window_flags()

    def _toggle_passthrough(self, checked: bool) -> None:
        self.cfg.set("mouse_passthrough", checked)
        self.cfg.save()
        self._apply_passthrough(checked)
        if checked:
            self.tray.showMessage(
                "DeskDear",
                "鼠标穿透已开启，角色将不再响应鼠标。\n可通过系统托盘图标右键菜单恢复。",
                QSystemTrayIcon.Information,
                5000,
            )

    def _toggle_roam(self, checked: bool) -> None:
        self.cfg.set("roam_enabled", checked)
        self.cfg.save()
        self.roam.start() if checked else self.roam.stop()

    def _toggle_reminder(self, checked: bool) -> None:
        self.cfg.set("reminder_enabled", checked)
        self.cfg.save()
        self.reminder.set_enabled(checked)

    def _toggle_autostart(self, checked: bool) -> None:
        try:
            autostart.set_enabled(checked)
            self.cfg.set("auto_start", checked)
            self.cfg.save()
        except OSError:
            self.tray.showMessage(
                "DeskDear", "设置开机自启失败，请检查系统权限。",
                QSystemTrayIcon.Warning, 4000,
            )

    # ================== 系统托盘 ==================
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self._make_tray_icon())
        self.tray.setToolTip("DeskDear 桌面助手")

        menu = QMenu()
        self._add_action(menu, "显示 / 隐藏", self.toggle_visible)
        self._add_action(menu, "打开聊天", self.toggle_chat)
        self._add_action(
            menu, "关闭鼠标穿透",
            lambda: self._toggle_passthrough(False),
        )
        menu.addSeparator()
        self._add_action(menu, "设置面板", self.open_settings)
        self._add_action(menu, "退出程序", self.quit_app)
        self.tray.setContextMenu(menu)

        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _make_tray_icon(self) -> QIcon:
        """复用 idle 状态第一帧作为托盘图标，无需额外素材。"""
        try:
            frames = self.player._load_raw(PetState.IDLE)  # 内部缓存读取
            if frames:
                return QIcon(frames[0].scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception:
            pass
        return self.style().standardIcon(QStyle.SP_ComputerIcon)

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self.toggle_visible()

    # ================== 退出 ==================
    def quit_app(self) -> None:
        self.chat_bubble.close()
        self.cfg.save()
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        # 关闭窗口不等于退出程序：隐藏到托盘继续驻留
        event.ignore()
        self.chat_bubble.hide()
        self.hide()
