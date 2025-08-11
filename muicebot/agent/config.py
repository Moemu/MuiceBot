from pathlib import Path
from typing import Dict, List, Optional

import yaml
from nonebot import get_plugin_config
from pydantic import BaseModel, Field

from muicebot.llm._config import ModelConfig

AGENTS_CONFIG_PATH = Path("configs/agents.yml")


class AgentPluginConfig(BaseModel):
    """Agent配置模型"""

    max_loop_count: int = Field(default=5, description="最大循环次数")
    api_call_interval: float = Field(default=1.0, description="API调用间隔")


agent_plugin_config = get_plugin_config(AgentPluginConfig)


class AgentConfig(ModelConfig):
    """Agent配置模型，继承自ModelConfig"""

    tools_list: List[str] = Field(default_factory=list, description="Agent可用的工具列表")
    max_loop_count: int = Field(default=5, description="最大循环次数")
    description: Optional[str] = Field(default=None, description="Agent描述")


class AgentResponse(BaseModel):
    """Agent响应模型"""

    result: str
    # Agent 只返回分析结果


def format_agent_output(
    agent_name: str,
    result: str,
) -> str:
    """
    格式化Agent输出，使其能够被主模型正确识别和利用

    Args:
        agent_name: Agent名称
        result: Agent原始结果

    Returns:
        格式化后的输出字符串
    """
    # 使用特殊标记包装Agent输出，帮助主模型识别这是工具返回的结果
    formatted_output = f"""
[AGENT_ANALYSIS_RESULT]
来源: {agent_name}
内容:
{result}
[AGENT_ANALYSIS_END]
"""
    return formatted_output.strip()


class AgentToolCall(BaseModel):
    """Agent工具调用模型"""

    name: str
    arguments: dict
    result: Optional[str] = None


class AgentConfigManager:
    """Agent配置管理器"""

    def __init__(self):
        self._configs: Dict[str, AgentConfig] = {}
        self._load_configs()

    def _load_configs(self):
        """加载Agent配置文件"""
        # 合并检查配置文件不存在和配置文件为空的情况
        if not AGENTS_CONFIG_PATH.exists():
            # 如果配置文件不存在，不自动创建默认配置
            # 用户需要明确决定是否使用Agent
            self._configs = {}
            return

        with open(AGENTS_CONFIG_PATH, "r", encoding="utf-8") as f:
            configs_dict = yaml.safe_load(f)

        # 如果配置文件为空或解析失败，不自动创建默认配置
        if not configs_dict:
            self._configs = {}
            return

        # 加载配置项
        self._configs = {}
        for name, config in configs_dict.items():
            # 使用Pydantic模型验证配置项
            self._configs[name] = AgentConfig(**config)

    def get_agent_config(self, agent_name: str) -> AgentConfig:
        """获取指定Agent的配置"""
        if agent_name not in self._configs:
            raise ValueError(f"Agent配置不存在: {agent_name}")
        return self._configs[agent_name]

    def list_agents(self) -> List[str]:
        """列出所有Agent"""
        return list(self._configs.keys())

    def reload_configs(self):
        """重新加载配置文件"""
        self._configs.clear()
        self._load_configs()

    def can_use_tools(self, agent_name: str) -> bool:
        """
        检查Agent是否可以使用工具
        工具调用的逻辑：
        1. 必须启用工具调用(function_call=True)
        2. 工具列表不能为空
        """
        if agent_name not in self._configs:
            return False

        config = self._configs[agent_name]
        # 检查是否启用工具调用且工具列表不为空
        return config.function_call and len(config.tools_list) > 0

    def get_available_tools(self, agent_name: str) -> List[str]:
        """
        获取Agent可用的工具列表
        """
        if agent_name not in self._configs:
            return []

        config = self._configs[agent_name]
        # 只有在启用工具调用时才返回工具列表
        if config.function_call:
            return config.tools_list
        else:
            return []
