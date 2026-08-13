# -*- coding: utf-8 -*-
"""配置管理：所有配置项持久化到本地 JSON 文件。"""
import copy
import json
import os

from core.resource_utils import app_dir

CONFIG_FILE_NAME = "user_config.json"

# 全部默认配置项
DEFAULT_CONFIG = {
    # ---- 窗口相关 ----
    "scale": 0.25,                   # 角色缩放比例（0.1 ~ 3.0，默认适配高清素材）
    "always_on_top": True,           # 窗口始终置顶
    "mouse_passthrough": False,      # 鼠标穿透（开启后需通过托盘菜单恢复）
    "auto_start": False,             # 开机自启（仅作记录，真实状态以注册表为准）
    # ---- 动画相关 ----
    "animation_speed": 0.75,          # 动画播放速度倍率（0.5 ~ 2.0）
    "skin_path": "assets/skin/girlfriend",  # 皮肤素材根目录（相对资源目录或绝对路径）
    "idle_to_sad_seconds": 30,       # 无交互多少秒后进入委屈状态
    "idle_to_sleepy_seconds": 45,    # 无交互多少秒后进入犯困状态
    # ---- 预留功能 ----
    "roam_enabled": False,           # 桌面随机漫游（预留接口，默认关闭）
    "reminder_enabled": False,       # 定时提醒（预留接口，默认关闭）
    "reminder_interval_minutes": 45, # 提醒间隔（分钟）
    # ---- LLM 聊天相关 ----
    "llm": {
        "base_url": "https://api.deepseek.com/v1",  # OpenAI 兼容接口地址
        "api_key": "",                              # API 密钥
        "model": "deepseek-v4-pro",                   # 模型名称
        "persona": "academic",                        # 对话风格：academic/concise/detailed
        "temperature": 0.7,                         # 采样温度
        "max_history": 30,                          # 上下文记忆的最大对话轮数
        "timeout_seconds": 30,                      # 请求超时时间（秒）
    },
}


class ConfigManager:
    """读写本地 JSON 配置，支持 "llm.api_key" 形式的点分键访问。"""

    def __init__(self, path: str | None = None):
        self._path = path or os.path.join(app_dir(), CONFIG_FILE_NAME)
        self._data = copy.deepcopy(DEFAULT_CONFIG)
        self.load()

    # ---------------- 基础读写 ----------------
    def load(self) -> None:
        """从磁盘加载配置，文件损坏时自动回退到默认值。"""
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                self._deep_merge(self._data, stored)
        except (OSError, json.JSONDecodeError):
            # 配置文件损坏不影响程序启动
            pass

    def save(self) -> None:
        """将当前配置写入磁盘。"""
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> None:
        """递归合并：已存储的值覆盖默认值，保留新增默认键。"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                ConfigManager._deep_merge(base[key], value)
            else:
                base[key] = value

    # ---------------- 点分键访问 ----------------
    def get(self, dotted_key: str, default=None):
        node = self._data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted_key: str, value) -> None:
        parts = dotted_key.split(".")
        node = self._data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    # ---------------- 类型便捷读取 ----------------
    def get_bool(self, key: str) -> bool:
        return bool(self.get(key, False))

    def get_float(self, key: str) -> float:
        try:
            return float(self.get(key, 0.0))
        except (TypeError, ValueError):
            return 0.0

    def get_int(self, key: str) -> int:
        try:
            return int(self.get(key, 0))
        except (TypeError, ValueError):
            return 0

    def get_str(self, key: str) -> str:
        value = self.get(key, "")
        return str(value) if value is not None else ""
