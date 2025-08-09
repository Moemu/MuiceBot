import os
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, field_validator

from ..llm._config import ModelConfig

AGENTS_CONFIG_PATH = Path("configs/agents.yml")


class AgentConfig(ModelConfig):
    """Agent配置模型，继承自ModelConfig"""

    tools_list: Optional[List[str]] = None
    max_loop_count: int = 5  # 默认最大循环次数
    description: Optional[str] = None  # Agent描述

    def __init__(self, **data):
        # 处理 tools_list 为 None 的情况
        if "tools_list" not in data or data["tools_list"] is None:
            data["tools_list"] = []

        # 如果没有指定max_loop_count，使用默认值
        if "max_loop_count" not in data:
            data["max_loop_count"] = self.get_default_max_loop_count()

        super().__init__(**data)

    @field_validator("max_loop_count", check_fields=False)
    @classmethod
    def validate_max_loop_count(cls, v):
        """验证最大循环次数"""
        if not isinstance(v, int) or v <= 0:
            raise ValueError("max_loop_count 必须是正整数")
        return v

    @classmethod
    def get_default_max_loop_count(cls):
        """获取默认最大循环次数"""
        try:
            return int(os.getenv("MUICE_AGENT_MAX_LOOP_COUNT", "5"))
        except ValueError:
            return 5

    @classmethod
    def get_default_api_call_interval(cls):
        """获取默认API调用间隔"""
        try:
            return float(os.getenv("MUICE_AGENT_API_CALL_INTERVAL", "1.0"))
        except ValueError:
            return 1.0


class AgentResponse(BaseModel):
    """Agent响应模型"""

    result: str
    need_continue: bool = False
    next_agent: Optional[str] = None
    next_task: Optional[str] = None


def format_agent_output(
    agent_name: str,
    result: str,
    need_continue: bool = False,
    next_agent: Optional[str] = None,
    next_task: Optional[str] = None,
) -> str:
    """
    格式化Agent输出，使其能够被主模型正确识别和利用

    Args:
        agent_name: Agent名称
        result: Agent原始结果
        need_continue: 是否需要继续调用其他Agent
        next_agent: 下一个要调用的Agent名称
        next_task: 下一个要执行的任务

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

处理指导:
1. 请仔细分析以上Agent的分析结果
2. 判断是否需要进一步处理或调用其他专业Agent
3. 如果需要继续调用，请明确指出要调用哪个Agent以及具体任务
4. 如果不需要继续调用，请直接基于以上分析结果回答用户问题

是否建议继续调用: {"是" if need_continue else "否"}
{"建议调用的Agent: " + next_agent if next_agent else ""}
{"建议执行的任务: " + next_task if next_task else ""}
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
        return config.function_call and config.tools_list is not None and len(config.tools_list) > 0

    def get_available_tools(self, agent_name: str) -> List[str]:
        """
        获取Agent可用的工具列表
        """
        if agent_name not in self._configs:
            return []

        config = self._configs[agent_name]
        # 只有在启用工具调用时才返回工具列表
        if config.function_call:
            return config.tools_list or []
        else:
            return []
