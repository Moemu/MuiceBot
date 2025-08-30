"""
Agent工具函数模块
"""

from typing import Any

from nonebot import logger
from pydantic import BaseModel, Field

from muicebot.agent.communication import AgentCommunication
from muicebot.agent.config import AgentConfigManager
from muicebot.agent.manager import AgentManager


class AgentTaskParameters(BaseModel):
    """Agent任务参数模型"""

    task: str = Field(
        description="要交给Agent处理的详细任务描述。请清晰、具体地描述任务目标、要求和期望结果，"
        "以便Agent能够准确理解和执行。"
    )


def create_agent_tool_description(agent_name: str, agent_description: str) -> dict[str, Any]:
    """
    创建Agent工具描述，复用现有的工具描述生成逻辑

    Args:
        agent_name: Agent名称
        agent_description: Agent描述

    Returns:
        Dict[str, Any]: 格式化后的工具描述
    """
    return {
        "type": "function",
        "function": {
            "name": agent_name,
            "description": agent_description,
            "parameters": AgentTaskParameters.model_json_schema(),
        },
    }


async def get_agent_list() -> list[dict[str, Any]]:
    """
    获取所有可用Agent的信息列表，格式化为工具调用格式

    Returns:
        List[Dict[str, Any]]: Agent信息列表，格式化为工具调用格式
    """
    agent_tools = []
    config_manager = AgentConfigManager.get_instance()
    agents = config_manager.list_agents()

    # 为每个Agent创建工具描述
    for agent_name in agents:
        try:
            config = config_manager.get_agent_config(agent_name)
            # Agent本身就是工具，无论是否启用工具调用都应该添加到工具列表中
            # 使用配置中的description字段，如果没有则不提供描述
            agent_description = config.description or f"Agent {agent_name}"

            agent_tool = create_agent_tool_description(agent_name, agent_description)
            agent_tools.append(agent_tool)
        except Exception as e:
            logger.warning(f"获取Agent配置失败，跳过该Agent: agent_name={agent_name}, error={e}")
            continue

    return agent_tools


def is_agent(agent_name: str) -> bool:
    """检查一个名称是否对应一个已配置的Agent"""
    config_manager = AgentConfigManager.get_instance()
    return agent_name in config_manager.list_agents()


async def call_agent(func: str, arguments: dict[str, str], message_id: str | None = None) -> str:
    """
    调用Agent并处理响应

    Args:
        func: Agent函数名
        arguments: Agent函数参数
        message_id: 消息ID，用于标识同一用户请求中的多次调用

    Returns:
        str: Agent调用结果
    """
    logger.info(f"Agent call 请求 {func}, 参数: {arguments}")
    agent_comm = AgentCommunication.get_instance()
    agent_manager = AgentManager.get_instance()
    # 使用message_id作为request_id，确保同一用户请求中的多次调用使用同一个任务链
    request_id = message_id
    response = await agent_comm.request_agent_assistance(func, arguments, request_id)
    result = agent_manager.handle_agent_response(response)
    logger.success(f"Agent call 成功，返回: {result}")
    return result
