# -*- coding: utf-8 -*-
"""可视化设置面板：修改全部配置项并持久化到 JSON。"""
import os

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.llm_client import PERSONA_LABELS


class SettingsDialog(QDialog):
    """设置对话框。保存后发出 applied 信号，由主窗口统一应用配置。"""

    applied = Signal()

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("DeskDear 设置")
        self.setMinimumWidth(460)

        self._build_ui()
        self._load_values()

    # ---------------- 界面 ----------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # ---- 外观与动画 ----
        appearance = QGroupBox("外观与动画", self)
        form = QFormLayout(appearance)

        self.spin_scale = QDoubleSpinBox()
        self.spin_scale.setRange(0.1, 3.0)
        self.spin_scale.setSingleStep(0.05)
        form.addRow("缩放比例", self.spin_scale)

        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.5, 2.0)
        self.spin_speed.setSingleStep(0.1)
        form.addRow("动画速度倍率", self.spin_speed)

        self.spin_sad = QSpinBox()
        self.spin_sad.setRange(10, 3600)
        self.spin_sad.setSuffix(" 秒")
        form.addRow("无交互进入委屈", self.spin_sad)

        self.spin_sleepy = QSpinBox()
        self.spin_sleepy.setRange(10, 7200)
        self.spin_sleepy.setSuffix(" 秒")
        form.addRow("无交互进入犯困", self.spin_sleepy)

        self.chk_top = QCheckBox("窗口始终置顶")
        form.addRow(self.chk_top)

        self.chk_passthrough = QCheckBox("鼠标穿透（开启后请用系统托盘菜单恢复）")
        form.addRow(self.chk_passthrough)

        # 皮肤选择
        skin_row = QWidget()
        skin_layout = QHBoxLayout(skin_row)
        skin_layout.setContentsMargins(0, 0, 0, 0)
        self.edit_skin = QLineEdit()
        self.edit_skin.setPlaceholderText("皮肤文件夹（需包含 idle 等状态子目录）")
        browse_btn = QPushButton("浏览…")
        browse_btn.clicked.connect(self._browse_skin)
        skin_layout.addWidget(self.edit_skin)
        skin_layout.addWidget(browse_btn)
        form.addRow("皮肤素材文件夹", skin_row)

        layout.addWidget(appearance)

        # ---- AI 聊天 ----
        llm_box = QGroupBox("AI 聊天（OpenAI 兼容接口，支持 DeepSeek）", self)
        llm_form = QFormLayout(llm_box)

        self.edit_base_url = QLineEdit()
        self.edit_base_url.setPlaceholderText("https://api.deepseek.com/v1")
        llm_form.addRow("接口地址", self.edit_base_url)

        self.edit_api_key = QLineEdit()
        self.edit_api_key.setEchoMode(QLineEdit.Password)
        self.edit_api_key.setPlaceholderText("sk-……")
        llm_form.addRow("API 密钥", self.edit_api_key)

        self.edit_model = QLineEdit()
        self.edit_model.setPlaceholderText("deepseek-v4-pro")
        llm_form.addRow("模型名称", self.edit_model)

        self.combo_persona = QComboBox()
        for key, label in PERSONA_LABELS.items():
            self.combo_persona.addItem(label, key)
        llm_form.addRow("对话风格", self.combo_persona)

        self.spin_temperature = QDoubleSpinBox()
        self.spin_temperature.setRange(0.0, 1.5)
        self.spin_temperature.setSingleStep(0.1)
        llm_form.addRow("随机性 temperature", self.spin_temperature)

        self.spin_history = QSpinBox()
        self.spin_history.setRange(1, 50)
        self.spin_history.setSuffix(" 轮")
        llm_form.addRow("上下文记忆", self.spin_history)

        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(5, 120)
        self.spin_timeout.setSuffix(" 秒")
        llm_form.addRow("请求超时", self.spin_timeout)

        layout.addWidget(llm_box)

        # ---- 按钮 ----
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self)
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ---------------- 数据加载 / 保存 ----------------
    def _load_values(self) -> None:
        cfg = self.cfg
        self.spin_scale.setValue(cfg.get_float("scale") or 0.25)
        self.spin_speed.setValue(cfg.get_float("animation_speed") or 1.0)
        self.spin_sad.setValue(cfg.get_int("idle_to_sad_seconds") or 60)
        self.spin_sleepy.setValue(cfg.get_int("idle_to_sleepy_seconds") or 90)
        self.chk_top.setChecked(cfg.get_bool("always_on_top"))
        self.chk_passthrough.setChecked(cfg.get_bool("mouse_passthrough"))
        self.edit_skin.setText(cfg.get_str("skin_path"))

        self.edit_base_url.setText(cfg.get_str("llm.base_url"))
        self.edit_api_key.setText(cfg.get_str("llm.api_key"))
        self.edit_model.setText(cfg.get_str("llm.model"))
        persona = cfg.get_str("llm.persona") or "academic"
        index = self.combo_persona.findData(persona)
        self.combo_persona.setCurrentIndex(max(0, index))
        self.spin_temperature.setValue(cfg.get_float("llm.temperature") or 0.8)
        self.spin_history.setValue(cfg.get_int("llm.max_history") or 10)
        self.spin_timeout.setValue(cfg.get_int("llm.timeout_seconds") or 30)

    def _browse_skin(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择皮肤素材文件夹", self.edit_skin.text())
        if not folder:
            return
        if not self._validate_skin(folder):
            QMessageBox.warning(
                self,
                "皮肤目录无效",
                "所选文件夹中没有可用的 idle 状态素材（PNG）。\n"
                "请确认目录结构形如：皮肤根目录/idle/xxx.png",
            )
            return
        self.edit_skin.setText(folder)

    @staticmethod
    def _validate_skin(folder: str) -> bool:
        """皮肤目录至少需包含 idle 子目录且其中有 PNG 帧。"""
        idle_dir = os.path.join(folder, "idle")
        if not os.path.isdir(idle_dir):
            return False
        return any(name.lower().endswith(".png") for name in os.listdir(idle_dir))

    def _on_save(self) -> None:
        if self.spin_sleepy.value() < self.spin_sad.value():
            QMessageBox.warning(self, "提示", "“进入犯困”的秒数不应小于“进入委屈”的秒数。")
            return

        cfg = self.cfg
        cfg.set("scale", round(self.spin_scale.value(), 2))
        cfg.set("animation_speed", round(self.spin_speed.value(), 2))
        cfg.set("idle_to_sad_seconds", self.spin_sad.value())
        cfg.set("idle_to_sleepy_seconds", self.spin_sleepy.value())
        cfg.set("always_on_top", self.chk_top.isChecked())
        cfg.set("mouse_passthrough", self.chk_passthrough.isChecked())
        cfg.set("skin_path", self.edit_skin.text().strip() or "assets/skin/girlfriend")

        cfg.set("llm.base_url", self.edit_base_url.text().strip())
        cfg.set("llm.api_key", self.edit_api_key.text().strip())
        cfg.set("llm.model", self.edit_model.text().strip() or "deepseek-v4-pro")
        cfg.set("llm.persona", self.combo_persona.currentData())
        cfg.set("llm.temperature", round(self.spin_temperature.value(), 2))
        cfg.set("llm.max_history", self.spin_history.value())
        cfg.set("llm.timeout_seconds", self.spin_timeout.value())

        cfg.save()
        self.applied.emit()
        self.accept()
