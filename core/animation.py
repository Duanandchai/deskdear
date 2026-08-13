# -*- coding: utf-8 -*-
"""动画状态机：加载 PNG 精灵序列帧并按状态独立帧率播放。

硬性规则实现要点：
1. 同一时刻只播放一种状态动画（单定时器驱动，切换即停止旧动画）；
2. 每种动画独立 FPS 配置，空闲状态使用低帧率以降低 CPU 占用；
3. 循环动画之间即时切换，无需等待当前循环结束；
4. 一次性动画播放完毕后发出信号，由上层强制回归 idle；
5. 素材目录按状态分类，帧数动态扫描，不受具体数量限制。
"""
import os

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap

from core.resource_utils import natural_key


class PetState:
    """8 种角色状态常量，取值与素材子文件夹名一一对应。"""

    IDLE = "idle"              # 待机循环（常驻基础状态）
    TOUCH_SHY = "touch_shy"    # 点击害羞（单次）
    HAPPY_JUMP = "happy_jump"  # 开心跳跃（单次）
    SAD = "sad"                # 委屈低落（循环）
    WAVE = "wave"              # 挥手打招呼（单次）
    SLEEPY = "sleepy"          # 犯困睡觉（循环）
    DAZE = "daze"              # 发呆思考（循环）
    DRAG = "drag"              # 被鼠标拖动（循环，2 张静态图低频交替）


# 每种动画的独立帧率与循环配置（帧率分离，空闲低帧率省 CPU）
STATE_META = {
    PetState.IDLE:       {"loop": True,  "fps": 5},
    PetState.TOUCH_SHY:  {"loop": False, "fps": 7},
    PetState.HAPPY_JUMP: {"loop": False, "fps": 8},
    PetState.SAD:        {"loop": True,  "fps": 4},
    PetState.WAVE:       {"loop": False, "fps": 7},
    PetState.SLEEPY:     {"loop": True,  "fps": 3},
    PetState.DAZE:       {"loop": True,  "fps": 4},
    PetState.DRAG:       {"loop": True,  "fps": 4},
}


class AnimationPlayer(QObject):
    """序列帧动画播放器。

    信号：
        frame_changed(QPixmap)   当前帧变化（已按缩放比例处理）
        one_shot_finished(str)   一次性动画播放完毕，参数为状态名
    """

    frame_changed = Signal(QPixmap)
    one_shot_finished = Signal(str)

    def __init__(self, skin_root: str, scale: float = 1.0, speed: float = 1.0, parent=None):
        super().__init__(parent)
        self.skin_root = skin_root
        self.scale = scale
        self.speed = max(0.1, speed)

        self._raw_cache: dict[str, list[QPixmap]] = {}     # 原始帧缓存 {状态: [QPixmap]}
        self._scaled_cache: dict[str, list[QPixmap]] = {}  # 缩放帧缓存
        self._frames: list[QPixmap] = []                   # 当前播放的帧序列
        self._index = 0
        self._state: str | None = None

        # 单定时器驱动：天然保证任何时刻只有一个动画在运行
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ---------------- 属性 ----------------
    @property
    def current_state(self) -> str | None:
        return self._state

    # ---------------- 外部控制 ----------------
    def play(self, state: str) -> None:
        """切换到指定状态播放。

        - 相同循环状态重复调用直接忽略（避免循环被打断重启）；
        - 一次性动画允许重复触发（重新播放）；
        - 其余情况立即停止旧动画并切换到新动画（即时切换）。
        """
        if state not in STATE_META:
            return
        if state == self._state and STATE_META[state]["loop"]:
            return
        self._timer.stop()
        self._state = state
        self._frames = self._get_frames(state)
        self._index = 0
        self.frame_changed.emit(self._frames[0])
        self._timer.start(self._interval_for(state))

    def stop(self) -> None:
        self._timer.stop()

    def set_skin_root(self, skin_root: str) -> None:
        """切换皮肤素材目录：清空缓存并重新加载当前状态。"""
        self.skin_root = skin_root
        self._raw_cache.clear()
        self._scaled_cache.clear()
        if self._state:
            state = self._state
            self._state = None  # 强制重新加载
            self.play(state)

    def set_scale(self, scale: float) -> None:
        """更新缩放比例：重建缩放缓存并立即刷新当前帧。"""
        self.scale = scale
        self._scaled_cache.clear()
        if self._state:
            self._frames = self._get_frames(self._state)
            self._index = min(self._index, len(self._frames) - 1)
            self.frame_changed.emit(self._frames[self._index])

    def set_speed(self, speed: float) -> None:
        """更新全局动画速度倍率。"""
        self.speed = max(0.1, speed)
        if self._state and self._timer.isActive():
            self._timer.setInterval(self._interval_for(self._state))

    # ---------------- 内部实现 ----------------
    def _interval_for(self, state: str) -> int:
        """根据状态 FPS 与速度倍率计算帧间隔（毫秒）。"""
        fps = STATE_META[state]["fps"]
        return max(15, int(1000.0 / (fps * self.speed)))

    def _tick(self) -> None:
        """推进到下一帧；一次性动画播完后停在末帧并发完成信号。"""
        self._index += 1
        if self._index >= len(self._frames):
            if STATE_META[self._state]["loop"]:
                self._index = 0  # 循环动画回卷
            else:
                self._index = len(self._frames) - 1
                self._timer.stop()
                self.one_shot_finished.emit(self._state)
                return
        self.frame_changed.emit(self._frames[self._index])

    def _get_frames(self, state: str) -> list[QPixmap]:
        """获取某状态的缩放帧序列（带缓存）。"""
        if state in self._scaled_cache:
            return self._scaled_cache[state]
        raw_frames = self._load_raw(state)
        if abs(self.scale - 1.0) < 1e-6:
            frames = raw_frames
        else:
            frames = [
                p.scaled(
                    max(1, int(p.width() * self.scale)),
                    max(1, int(p.height() * self.scale)),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                for p in raw_frames
            ]
        self._scaled_cache[state] = frames
        return frames

    def _load_raw(self, state: str) -> list[QPixmap]:
        """从 assets 目录加载某状态的全部 PNG 帧（自然排序，帧数自适应）。"""
        if state in self._raw_cache:
            return self._raw_cache[state]
        frames: list[QPixmap] = []
        folder = os.path.join(self.skin_root, state)
        if os.path.isdir(folder):
            files = [f for f in os.listdir(folder) if f.lower().endswith(".png")]
            files.sort(key=natural_key)
            for name in files:
                pixmap = QPixmap(os.path.join(folder, name))
                if not pixmap.isNull():
                    frames.append(pixmap)
        if not frames:
            # 素材缺失时绘制占位图，保证程序不崩溃
            frames = [self._placeholder(state)]
        self._raw_cache[state] = frames
        return frames

    @staticmethod
    def _placeholder(state: str) -> QPixmap:
        """素材缺失时的占位图（半透明圆角框 + 状态名）。"""
        pixmap = QPixmap(220, 260)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor(200, 120, 160))
        painter.setBrush(QColor(255, 255, 255, 120))
        painter.drawRoundedRect(4, 4, 212, 252, 16, 16)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, f"缺少素材\n{state}")
        painter.end()
        return pixmap
