from __future__ import annotations

import atexit
import os
import threading
import time
from pathlib import Path
from typing import Callable, List, Literal, Optional

import yaml as yaml_
from nonebot import get_plugin_config, logger
from pydantic import BaseModel
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from .llm import EmbeddingConfig, ModelConfig

MODELS_CONFIG_PATH = Path("configs/models.yml").resolve()
SCHEDULES_CONFIG_PATH = Path("configs/schedules.yml").resolve()
EMBEDDINGS_CONFIG_PATH = Path("configs/embeddings.yml").resolve()

_model_config_manager: Optional["ModelConfigManager"] = None
_embeddings_configs: dict[str, EmbeddingConfig] = {}


class PluginConfig(BaseModel):
    log_level: str = "INFO"
    """日志等级"""
    muice_nicknames: list = ["muice"]
    """沐雪的自定义昵称，作为消息前缀条件响应信息事件"""
    telegram_proxy: str | None = None
    """telegram代理，这个配置项用于获取图片时使用"""
    enable_builtin_plugins: bool = True
    """启用内嵌插件"""
    max_history_epoch: int = 0
    """最大历史轮数"""
    enable_adapters: list = ["nonebot.adapters.onebot.v11", "nonebot.adapters.onebot.v12"]
    """启用的 Nonebot 适配器"""
    input_timeout: int = 0
    """输入等待时间"""
    default_template: Optional[str] = "Muice"
    """默认使用人设模板名称"""
    thought_process_mode: Literal[0, 1, 2] = 2
    """针对 Deepseek-R1 等思考模型的思考过程提取模式"""
    enable_embedding_cache: bool = True
    """启用嵌入缓存"""


plugin_config = get_plugin_config(PluginConfig)


class Schedule(BaseModel):
    id: str
    """调度器 ID"""
    trigger: Literal["cron", "interval"]
    """调度器类别"""
    ask: Optional[str] = None
    """向大语言模型询问的信息"""
    say: Optional[str] = None
    """直接输出的信息"""
    args: dict[str, int]
    """调度器参数"""
    target: str
    """目标id；若为群聊则为 group_id 或者 channel_id，若为私聊则为 user_id"""
    probability: int = 1
    """触发几率"""


def get_schedule_configs() -> List[Schedule]:
    """
    从配置文件 `configs/schedules.yml` 中获取所有调度器配置

    如果没有该文件，返回空列表
    """
    if not os.path.isfile(SCHEDULES_CONFIG_PATH):
        return []

    with open(SCHEDULES_CONFIG_PATH, "r", encoding="utf-8") as f:
        configs = yaml_.safe_load(f)

    if not configs:
        return []

    schedule_configs = []

    for schedule_id, config in configs.items():
        config["id"] = schedule_id
        schedule_config = Schedule(**config)
        schedule_configs.append(schedule_config)

    return schedule_configs


class ConfigFileHandler(FileSystemEventHandler):
    """配置文件变化处理器"""

    def __init__(self, callback: Callable):
        self.callback = callback
        self.last_modified = time.time()
        # 防止一次修改触发多次回调
        self.cooldown = 1  # 冷却时间（秒）

    def on_modified(self, event):
        if event.is_directory:  # 检查是否是文件而不是目录
            return

        current_time = time.time()
        if current_time - self.last_modified > self.cooldown:
            self.last_modified = current_time
            self.callback()


class ModelConfigManager:
    """模型配置管理器"""

    _instance: Optional["ModelConfigManager"] = None
    _lock = threading.Lock()
    _initialized: bool
    configs: dict[str, ModelConfig]

    def __new__(cls):
        """确保实例在单例模式下运行"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ModelConfigManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self.configs: dict[str, ModelConfig] = {}
        """所有模型配置"""
        self.default_config = None
        """默认模型配置"""
        self.observer: Optional[BaseObserver] = None
        """文件监视器"""
        self._listeners: List[Callable] = []
        """监听器列表"""

        self._load_configs()
        self._start_file_watcher()

        self._initialized = True

    def _load_configs(self):
        """加载配置文件"""
        if not os.path.isfile(MODELS_CONFIG_PATH):
            raise FileNotFoundError("configs/models.yml 不存在！请先创建")

        with open(MODELS_CONFIG_PATH, "r", encoding="utf-8") as f:
            configs_dict = yaml_.safe_load(f)

        if not configs_dict:
            raise ValueError("configs/models.yml 为空，请先至少定义一个模型配置")

        self.configs = {}
        for name, config in configs_dict.items():
            self.configs[name] = ModelConfig(**config)
            # 未指定模板时，使用默认模板
            self.configs[name].template = self.configs[name].template or plugin_config.default_template
            if config.get("default"):
                self.default_config = self.configs[name]

        if not self.default_config and self.configs:
            # 如果没有指定默认配置，使用第一个
            self.default_config = next(iter(self.configs.values()))

    def _start_file_watcher(self):
        """启动文件监视器"""
        if self.observer is not None:
            self.observer.stop()

        self.observer = Observer()
        event_handler = ConfigFileHandler(self._on_config_changed)
        self.observer.schedule(event_handler, str(Path(MODELS_CONFIG_PATH).parent), recursive=False)
        self.observer.start()

    def _on_config_changed(self):
        """配置文件变化时的回调函数"""
        try:
            # old_configs = self.configs.copy()
            old_default = self.default_config

            self._load_configs()

            # 通知所有注册的监听器
            for listener in self._listeners:
                listener(self.default_config, old_default)

        except Exception as e:
            logger.error(f"重新加载配置文件失败: {e}")

    def register_listener(self, listener: Callable):
        """
        注册配置变化监听器

        :param listener: 回调函数，接收两个参数：新的默认配置和旧的默认配置
        """
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unregister_listener(self, listener: Callable):
        """取消注册配置变化监听器"""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def get_model_config(self, model_config_name: Optional[str] = None) -> ModelConfig:
        """获取指定模型的配置"""
        if model_config_name in [None, ""]:
            if not self.default_config:
                raise ValueError("没有找到默认模型配置！请确保存在至少一个有效的配置项！")
            return self.default_config

        elif model_config_name in self.configs:
            return self.configs[model_config_name]

        else:
            logger.warning(f"指定的模型配置 '{model_config_name}' 不存在！")
            raise ValueError(f"指定的模型配置 '{model_config_name}' 不存在！")

    def stop_watcher(self):
        """停止文件监视器"""
        if self.observer is None:
            return

        self.observer.stop()
        self.observer.join()


def get_model_config_manager() -> ModelConfigManager:
    global _model_config_manager
    if _model_config_manager is None:
        _model_config_manager = ModelConfigManager()
        atexit.register(_model_config_manager.stop_watcher)
    return _model_config_manager


def get_model_config(model_config_name: Optional[str] = None) -> ModelConfig:
    """
    从配置文件 `configs/models.yml` 中获取指定模型的配置对象

    :param model_config_name: (可选)模型配置名称。若为空，则先寻找配置了 `default: true` 的首个配置项，若失败就再寻找首个配置项

    :raise FileNotFoundError: 配置文件不存在
    """
    model_config_manager = get_model_config_manager()
    return model_config_manager.get_model_config(model_config_name)


def get_embedding_model_config(embedding_config_name: Optional[str] = None) -> EmbeddingConfig:
    """
    从配置文件 `configs/models.yml` 中获取指定模型的配置对象

    :param embedding_config_name: (可选)模型配置名称。若为空，则先寻找配置了 `default: true` 的首个配置项，若失败就再寻找首个配置项

    :raise FileNotFoundError: 嵌入配置文件 `configs/embeddings.yml` 不存在或为空
    :raise ValueError: 指定的嵌入模型配置名不存在
    """
    if not _embeddings_configs:
        raise FileNotFoundError("嵌入配置文件 `configs/embeddings.yml` 不存在或为空")

    if not embedding_config_name:
        for config in _embeddings_configs.values():
            if config.default:
                return config

        return next(iter(_embeddings_configs.values()))

    embeddings_config = _embeddings_configs.get(embedding_config_name, None)

    if embeddings_config:
        return embeddings_config

    raise ValueError(f"指定的嵌入模型配置名: {embedding_config_name} 不存在")


def load_embedding_model_config():
    global _embeddings_configs

    if not os.path.isfile(EMBEDDINGS_CONFIG_PATH):
        _embeddings_configs = {}
        return

    with open(EMBEDDINGS_CONFIG_PATH, "r", encoding="utf-8") as f:
        configs = yaml_.safe_load(f)

    if not configs:
        _embeddings_configs = {}
        return

    _embeddings_configs = {}

    for name, config in configs.items():
        _embeddings_configs[name] = EmbeddingConfig(**config)
