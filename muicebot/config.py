import os
from pathlib import Path
from typing import List, Literal, Optional

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
    muice_nicknames: list = []
    """沐雪的自定义昵称，作为消息前缀条件响应信息事件"""
    telegram_proxy: str | None = None
    """telegram代理，这个配置项用于获取图片时使用"""


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


class Config(BaseModel):
    model: ModelConfig
    """configs.yml 中的模型配置"""
    schedule: List[Schedule]
    """调度器配置列表"""

    muice_nicknames: list = plugin_config.muice_nicknames
    """沐雪的自定义昵称，作为消息前缀条件响应信息事件"""

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
