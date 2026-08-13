# -*- coding: utf-8 -*-
"""桌面悬浮圆角聊天气泡。

- 无边框圆角半透明窗口，可拖动标题栏移动；
- 网络请求在工作线程中执行，不阻塞界面与桌宠动画；
- 内置简易对话上下文记忆（保留最近 N 轮，随配置调整）。
"""
import html
import markdown
import sys

from PySide6.QtCore import QEvent, Qt, QThread, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizeGrip,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core.llm_client import LLMClient, LLMError

# ---- Windows 无边框窗口原生移动/缩放支持 ----
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _WM_NCHITTEST = 0x0084
    _HTCLIENT = 1
    _HTCAPTION = 2
    _HTLEFT = 10
    _HTRIGHT = 11
    _HTTOP = 12
    _HTTOPLEFT = 13
    _HTTOPRIGHT = 14
    _HTBOTTOM = 15
    _HTBOTTOMLEFT = 16
    _HTBOTTOMRIGHT = 17

_RESIZE_BORDER = 8    # 边缘缩放检测宽度（像素）
_TITLE_BAR_H = 36     # 可拖动移动的标题栏高度（像素）


class ChatWorker(QThread):
    """后台线程执行 LLM 流式请求，避免阻塞主线程动画。"""

    chunk_received = Signal(str)   # 流式片段
    succeeded = Signal(str)        # 完整回复
    failed = Signal(str)

    def __init__(self, client: LLMClient, messages: list[dict], parent=None):
        super().__init__(parent)
        self._client = client
        self._messages = messages

    def run(self) -> None:
        try:
            full_text = ""
            for chunk in self._client.chat_stream(self._messages):
                full_text += chunk
                self.chunk_received.emit(chunk)
            self.succeeded.emit(full_text if full_text else "（返回内容为空）")
        except LLMError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # 兜底：任何意外都不能让程序崩溃
            self.failed.emit(f"出现了一点小问题：{exc}")


class ChatBubble(QWidget):
    """圆角聊天气泡窗口。"""

    def __init__(self, cfg, pet=None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.pet = pet                # 桌宠主窗口（用于互动计时复位、定位）
        self.history: list[dict] = []  # 对话上下文（user/assistant 交替）
        self._worker: ChatWorker | None = None
        self._title_drag_offset = None
        # 流式渲染状态
        self._stream_buffer: str = ""       # 当前流式回复的累积文本
        self._stream_start_pos: int = -1     # 流式内容在文档中的起始位置

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(320, 360)
        self.resize(420, 520)

        self._build_ui()

    # ---------------- 界面构建 ----------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        panel = QFrame(self)
        panel.setObjectName("panel")
        root.addWidget(panel)
        panel.setStyleSheet(
            "QFrame#panel { background: rgba(255,255,255,240);"
            " border: 1px solid #f472b6; border-radius: 14px; }"
            "QLabel#title { color: #db2777; font-weight: bold; padding-left: 4px; }"
            "QPushButton#closeBtn { border: none; color: #9ca3af; font-size: 16px;"
            " font-weight: 900; border-radius: 8px; padding: 2px 8px; }"
            "QPushButton#closeBtn:hover { color: white; background: #f472b6; }"
            "QTextBrowser#view { border: none; background: transparent; }"
            "QLineEdit { border: 1px solid #f9a8d4; border-radius: 10px; padding: 6px 8px; }"
            "QPushButton#sendBtn { background: #ec4899; color: white; border: none;"
            " border-radius: 10px; padding: 6px 14px; }"
            "QPushButton#sendBtn:hover { background: #db2777; }"
            "QPushButton#sendBtn:disabled { background: #f9a8d4; }"
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(8)

        # 标题栏（可拖动）
        title_row = QHBoxLayout()
        self.title = QLabel("DeskDear 助手", panel)
        self.title.setObjectName("title")
        self.title.installEventFilter(self)
        close_btn = QPushButton("×", panel)
        close_btn.setObjectName("closeBtn")
        close_btn.setFixedSize(36, 28)
        close_btn.clicked.connect(self.hide)
        title_row.addWidget(close_btn)
        title_row.addStretch(1)
        title_row.addWidget(self.title)
        layout.addLayout(title_row)

        # 消息区
        self.view = QTextBrowser(panel)
        self.view.setObjectName("view")
        self.view.setMinimumHeight(220)
        self.view.setOpenExternalLinks(True)
        self.view.document().setDefaultStyleSheet(
            "pre { background-color: #f3f4f6; border: 1px solid #d1d5db;"
            " border-radius: 4px; padding: 6px; }"
            "code { font-family: Consolas, 'Courier New', monospace; }"
            "table { border-collapse: collapse; }"
            "th, td { border: 1px solid #d1d5db; padding: 4px 8px; }"
        )
        layout.addWidget(self.view)

        # 输入行
        input_row = QHBoxLayout()
        self.input = QLineEdit(panel)
        self.input.setPlaceholderText("输入问题…")
        self.input.returnPressed.connect(self._send)
        self.send_btn = QPushButton("发送", panel)
        self.send_btn.setObjectName("sendBtn")
        self.send_btn.clicked.connect(self._send)
        input_row.addWidget(self.input)
        input_row.addWidget(self.send_btn)
        layout.addLayout(input_row)

        # 右下角调整大小手柄
        grip_row = QHBoxLayout()
        grip_row.addStretch(1)
        grip_row.addWidget(QSizeGrip(panel))
        layout.addLayout(grip_row)

    # ---------------- 标题栏拖动 ----------------
    def eventFilter(self, obj, event) -> bool:
        if obj is self.title:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._title_drag_offset = (
                    event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                )
                return True
            if event.type() == QEvent.MouseMove and self._title_drag_offset is not None:
                if event.buttons() & Qt.LeftButton:
                    self.move(event.globalPosition().toPoint() - self._title_drag_offset)
                return True
            if event.type() == QEvent.MouseButtonRelease:
                self._title_drag_offset = None
                return True
        return super().eventFilter(obj, event)

    # ---------------- Windows 原生移动/缩放 ----------------
    def nativeEvent(self, eventType, message):
        """拦截 WM_NCHITTEST，让无边框窗口支持原生拖动移动与边缘缩放。"""
        if sys.platform == "win32" and eventType == b"windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == _WM_NCHITTEST:
                    pt = msg.pt
                    geo = self.geometry()
                    wx = pt.x - geo.x()
                    wy = pt.y - geo.y()
                    w = self.width()
                    h = self.height()

                    # 优先排除交互控件（按钮、输入框等），
                    # 避免边缘缩放区把关闭按钮等遮住导致无法点击
                    child = self.childAt(wx, wy)
                    if child is not None and isinstance(
                        child, (QPushButton, QLineEdit, QTextBrowser)
                    ):
                        return (True, _HTCLIENT)

                    # 边缘缩放检测（窗口尺寸过小时跳过）
                    if w > _RESIZE_BORDER * 2 and h > _RESIZE_BORDER * 2:
                        left = wx <= _RESIZE_BORDER
                        right = wx >= w - _RESIZE_BORDER
                        top = wy <= _RESIZE_BORDER
                        bottom = wy >= h - _RESIZE_BORDER

                        if top and left:
                            return (True, _HTTOPLEFT)
                        if top and right:
                            return (True, _HTTOPRIGHT)
                        if bottom and left:
                            return (True, _HTBOTTOMLEFT)
                        if bottom and right:
                            return (True, _HTBOTTOMRIGHT)
                        if left:
                            return (True, _HTLEFT)
                        if right:
                            return (True, _HTRIGHT)
                        if top:
                            return (True, _HTTOP)
                        if bottom:
                            return (True, _HTBOTTOM)

                    # 标题栏拖动移动
                    if wy <= _TITLE_BAR_H:
                        return (True, _HTCAPTION)
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    # ---------------- 对外接口 ----------------
    def show_near(self, pet_rect) -> None:
        """在桌宠附近弹出气泡（优先显示在角色上方，自动做屏幕边界约束）。"""
        self.show()
        self.raise_()
        x = pet_rect.center().x() - self.width() // 2
        y = pet_rect.top() - self.height() - 12
        screen = QApplication.screenAt(pet_rect.center()) or QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            x = max(avail.left(), min(x, avail.right() - self.width() + 1))
            y = max(avail.top(), min(y, avail.bottom() - self.height() + 1))
        self.move(x, y)
        self.input.setFocus()

    # ---------------- 聊天逻辑 ----------------
    def _send(self) -> None:
        text = self.input.text().strip()
        if not text or self._worker is not None:
            return
        self.input.clear()
        self._append_message("user", text)
        self.history.append({"role": "user", "content": text})
        self._trim_history()

        # 从最新配置构建客户端，设置面板修改后立即生效
        client = LLMClient.from_config(self.cfg)
        messages = client.build_messages(self.history)

        self._set_busy(True)

        # 插入 AI 标签 + "正在思考"提示，记录流式内容起始位置
        cursor = self.view.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._stream_start_pos = cursor.position()
        cursor.insertHtml(
            '<p align="left" style="background-color: #fce7f3; color:#db2777;'
            ' font-weight:bold; margin:8px 0 2px 0; padding:6px 10px;">AI</p>'
        )
        cursor.insertHtml(
            '<p align="left" style="color:#9ca3af; font-style:italic;'
            ' margin:0 0 8px 0; padding:0 10px;">正在思考中...</p>'
        )
        self._stream_buffer = ""

        self._worker = ChatWorker(client, messages, self)
        self._worker.chunk_received.connect(self._on_chunk)
        self._worker.succeeded.connect(self._on_reply)
        self._worker.failed.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

        # 聊天也算一次互动，重置闲置计时
        if self.pet is not None:
            self.pet.register_interaction()

    def _on_chunk(self, chunk: str) -> None:
        """流式片段到达：增量重新渲染当前 AI 回复区块（思考提示自动被移除）。"""
        self._stream_buffer += chunk
        cursor = self.view.textCursor()
        cursor.setPosition(self._stream_start_pos)
        cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertHtml(
            '<p align="left" style="background-color: #fce7f3; color:#db2777;'
            ' font-weight:bold; margin:8px 0 2px 0; padding:6px 10px;">AI</p>'
        )
        md_html = markdown.markdown(
            self._stream_buffer, extensions=["fenced_code", "tables", "nl2br"]
        )
        cursor.insertHtml(md_html)
        # 与下一条消息留空行分隔
        cursor.insertHtml('<p style="margin:6px 0;">&nbsp;</p>')
        scrollbar = self.view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_reply(self, text: str) -> None:
        """流式结束：将完整回复写入历史（界面已在流式过程中渲染完成）。"""
        self.history.append({"role": "assistant", "content": text})
        self._trim_history()
        self._stream_buffer = ""
        self._stream_start_pos = -1

    def _on_error(self, message: str) -> None:
        # 清理流式渲染残留
        if self._stream_start_pos >= 0:
            cursor = self.view.textCursor()
            cursor.setPosition(self._stream_start_pos)
            cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
        self._stream_buffer = ""
        self._stream_start_pos = -1
        # 失败的对话不计入上下文记忆
        if self.history and self.history[-1].get("role") == "user":
            self.history.pop()
        self._append_message("system", message)

    def _on_worker_finished(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self.send_btn.setEnabled(not busy)
        self.input.setEnabled(not busy)
        if not busy:
            self.input.setFocus()

    def _trim_history(self) -> None:
        """上下文记忆：只保留最近 N 轮对话（一轮 = 一问一答）。"""
        max_rounds = max(1, self.cfg.get_int("llm.max_history") or 10)
        self.history = self.history[-max_rounds * 2:]

    # ---------------- 消息渲染 ----------------
    def _append_message(self, role: str, text: str) -> None:
        cursor = self.view.textCursor()
        cursor.movePosition(QTextCursor.End)
        if role == "user":
            safe = html.escape(text).replace("\n", "<br>")
            cursor.insertHtml(
                '<p align="right" style="background-color: #dbeafe; color:#1d4ed8;'
                ' margin:8px 0; padding:6px 10px;">'
                f"我：{safe}</p>"
            )
        elif role == "assistant":
            md_html = markdown.markdown(
                text, extensions=["fenced_code", "tables", "nl2br"]
            )
            cursor.insertHtml(
                '<p align="left" style="background-color: #fce7f3; color:#db2777;'
                ' font-weight:bold; margin:8px 0 2px 0; padding:6px 10px;">AI：</p>'
            )
            cursor.insertHtml(md_html)
        else:
            safe = html.escape(text).replace("\n", "<br>")
            cursor.insertHtml(
                '<p align="center" style="color:#9ca3af; font-size:11px; margin:8px 0;">'
                f"{safe}</p>"
            )
        # 消息间留空行分隔
        cursor.insertHtml('<p style="margin:6px 0;">&nbsp;</p>')
        scrollbar = self.view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
