import os
from pathlib import Path
from typing import List, Literal, Optional, ClassVar

import yaml as yaml_
from nonebot import get_plugin_config
from pydantic import BaseModel

from .llm import ModelConfig

MODELS_CONFIG_PATH = Path("configs/models.yml").resolve()
SCHEDULES_CONFIG_PATH = Path("configs/schedules.yml").resolve()
PLUGINS_CONFIG_PATH = Path("configs/plugins.yml").resolve()


class PluginConfig(BaseModel):
    log_level: str = "INFO"
    """日志等级"""
    telegram_proxy: str | None = None
    """telegram代理，这个配置项用于获取图片时使用"""
    plugins_dir: list = []
    """自定义插件加载目录"""
    enable_builtin_plugins: bool = True
    """启用内嵌插件"""
    is_random_reply: bool = False
    """是否开启随机回复(实验性选项)"""


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
    target: dict
    """指定发送信息的目标用户/群聊"""


class RandomReplyConfig(BaseModel):
    RANDOM_REPLY_CONFIG_PATH: ClassVar[Path] = Path("configs/random_reply.yml").resolve()

    including_nicknames: list = ["沐雪", "muice", "雪雪", "Muice"]
    """句中触发词列表"""
    including_nicknames_trigger_coefficient: float = 0.05
    """句中触发词触发系数"""
    beginning_trigger_words: list = ["沐雪", "muice", "雪", "Muice"]
    """句首触发词列表"""
    beginning_trigger_coefficient: float = 0.1
    """句首触发词触发系数"""
    random_trigger_probability_coefficient: float = 0.01
    """任意消息触发概率"""
    active_time_ranges: list = [("22:00", "02:00"), ("09:00", "18:00")]
    """活跃时间段"""
    active_coefficient: float = 1
    """活跃时间段系数"""
    unactive_coefficient: float = 0.5
    """非活跃时间段系数"""

    @classmethod
    def load_config(cls) -> 'RandomReplyConfig':
        """
        从 YAML 配置文件加载配置并返回初始化后的 RandomReplyConfig 实例

        Returns:
            RandomReplyConfig: 初始化后的配置实例
        """
        if not cls.RANDOM_REPLY_CONFIG_PATH.exists():
            return cls()
        with open(cls.RANDOM_REPLY_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config_data = yaml_.safe_load(f) or {}
        return cls(**config_data)


class Config(BaseModel):
    model: ModelConfig
    """configs.yml 中的模型配置"""
    schedule: List[Schedule]
    """调度器配置列表"""

    class Config:
        extra = "allow"


def get_schedule_configs() -> List[Schedule]:
    """
    从配置文件 `configs/schedules.yml` 中获取所有调度器配置

    如果没有该文件，返回空列表
    """
    if not os.path.isfile(SCHEDULES_CONFIG_PATH):
        return []

    with open(SCHEDULES_CONFIG_PATH, "r", encoding="utf-8") as f:
        configs = yaml_.load(f, Loader=yaml_.FullLoader)

    if not configs:
        return []

    schedule_configs = []

    for schedule_id, config in configs.items():
        config["id"] = schedule_id
        schedule_config = Schedule(**config)
        schedule_configs.append(schedule_config)

    return schedule_configs


def get_model_config(model_config_name: Optional[str] = None) -> ModelConfig:
    """
    从配置文件 `configs/models.yml` 中获取指定模型的配置文件

    :model_config_name: (可选)模型配置名称。若为空，则先寻找配置了 `default: true` 的首个配置项，若失败就再寻找首个配置项
    若都不存在，则抛出 `FileNotFoundError`
    """
    if not os.path.isfile(MODELS_CONFIG_PATH):
        raise FileNotFoundError("configs/models.yml 不存在！请先创建")

    with open(MODELS_CONFIG_PATH, "r", encoding="utf-8") as f:
        configs = yaml_.load(f, Loader=yaml_.FullLoader)

    if not configs:
        raise ValueError("configs/models.yml 为空，请先至少定义一个模型配置")

    if model_config_name in [None, ""]:
        model_config = next((config for config in configs.values() if config.get("default")), None)  # 尝试获取默认配置
        if not model_config:
            model_config = next(iter(configs.values()), None)  # 尝试获取第一个配置
    elif model_config_name in configs:
        model_config = configs.get(model_config_name, {})
    else:
        raise ValueError("指定的模型配置不存在！")

    if not model_config:
        raise FileNotFoundError("configs/models.yml 中不存在有效的模型配置项！")

    model_config = ModelConfig(**model_config)

    return model_config

