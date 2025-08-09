"""
Agent工具函数模块
"""

from typing import Any, Dict, List, Optional

from ..plugin.func_call import get_function_calls
from ..plugin.mcp import get_mcp_list
from .config import AgentConfigManager


async def get_agent_list() -> List[Dict[str, Any]]:
    """
    获取所有可用Agent的信息列表，格式化为工具调用格式

    Returns:
        List[Dict[str, Any]]: Agent信息列表，格式化为工具调用格式
    """
    agent_tools = []
    config_manager = AgentConfigManager()
    agents = config_manager.list_agents()

    # 为每个Agent创建工具描述
    for agent_name in agents:
        try:
            config = config_manager.get_agent_config(agent_name)
            # Agent本身就是工具，无论是否启用工具调用都应该添加到工具列表中
            # 获取Agent可用的工具列表
            available_tools = await _get_agent_available_tools(config.tools_list)
            if available_tools:
                tools_description = ", ".join(
                    [tool.get("function", {}).get("name", "unknown") for tool in available_tools]
                )
                # 获取Agent配置中的最大循环次数
                max_loops = config.max_loop_count
                # 使用配置中的description字段，如果没有则使用默认描述
                agent_description = (
                    config.description
                    or f"调用{agent_name} Agent处理任务。该Agent可以使用以下工具: {tools_description}。"
                    f"这是一个任务链工具，最多可以循环调用{max_loops}次。请根据任务的复杂程度和完成情况决定是否需要继续调用。"
                )
                agent_tool = {
                    "type": "function",
                    "function": {
                        "name": f"agent_{agent_name}",
                        "description": agent_description,
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "task": {"type": "string", "description": f"要交给{agent_name} Agent处理的任务描述"}
                            },
                            "required": ["task"],
                        },
                    },
                }
            else:
                # 如果没有可用工具，提供一个通用的Agent工具
                # 获取Agent配置中的最大循环次数
                max_loops = config.max_loop_count
                # 使用配置中的description字段，如果没有则使用默认描述
                agent_description = (
                    config.description
                    or f"调用{agent_name} Agent处理任务。注意：如果Agent的处理结果不完整或需要进一步处理，"
                    f"你可以再次调用该Agent或其他Agent继续处理，最多可以循环调用{max_loops}次。"
                )
                agent_tool = {
                    "type": "function",
                    "function": {
                        "name": f"agent_{agent_name}",
                        "description": agent_description,
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "task": {"type": "string", "description": f"要交给{agent_name} Agent处理的任务描述"}
                            },
                            "required": ["task"],
                        },
                    },
                }
            agent_tools.append(agent_tool)
        except Exception as e:
            from nonebot import logger

            logger.warning(f"获取Agent配置失败，跳过该Agent: agent_name={agent_name}, error={e}")
            continue

    return agent_tools


async def _get_agent_available_tools(tools_list: Optional[List[str]]) -> List[Dict[str, Any]]:
    """
    获取Agent可用的工具列表

    Args:
        tools_list: Agent配置的工具名称列表

    Returns:
        List[Dict[str, Any]]: 可用工具列表
    """
    available_tools = []
    tools_list = tools_list or []

    # 获取Function Call工具
    function_calls = get_function_calls()
    for tool_name in tools_list:
        if tool_name in function_calls:
            available_tools.append(function_calls[tool_name].data())

    # 获取MCP工具
    try:
        mcp_tools = await get_mcp_list()
        for tool in mcp_tools:
            # 检查工具名称是否在配置的工具列表中
            if tool.get("function", {}).get("name") in tools_list:
                available_tools.append(tool)
    except Exception as e:
        from nonebot import logger

        logger.warning(f"MCP工具加载失败，仅使用Function Call工具: error={e}")

    return available_tools
