from nonebot import logger

from muicebot.agent.config import AgentConfigManager
from muicebot.plugin.func_call import get_function_list
from muicebot.plugin.mcp import get_mcp_list
from muicebot.plugin.mcp.config import get_mcp_server_config


class AgentToolLoader:
    """Agent通用工具加载器"""

    def __init__(self) -> None:
        pass

    async def load_agent_tools(self, agent_name: str, tools_list: list[str] | None = None) -> list[dict]:
        """
        为指定Agent加载工具

        Args:
            agent_name: Agent名称
            tools_list: 工具列表，默认为空列表，如果为None则从配置中获取

        Returns:
            工具列表
        """
        # 如果没有提供工具列表，从配置中获取
        if tools_list is None:
            config_manager = AgentConfigManager.get_instance()
            tools_list = config_manager.get_available_tools(agent_name)

        # 加载工具
        logger.info(f"为Agent加载工具: agent={agent_name}, tools_count={len(tools_list or [])}")
        tools = await self._load_tools_from_sources(tools_list or [])

        logger.debug(f"工具加载完成: agent={agent_name}, loaded_tools={len(tools)}")
        return tools

    async def _load_tools_from_sources(self, tools_list: list[str]) -> list[dict]:
        """
        从各种来源加载工具 - 使用muicebot的工具调用机制

        Args:
            tools_list: 工具名称列表

        Returns:
            工具列表
        """
        available_tools = []
        tools_set = set(tools_list)
        mcp_server_names = set(get_mcp_server_config().keys())

        # 获取所有可用的Function Call工具
        try:
            function_tools = await get_function_list()
            # 按工具名称过滤Function Call工具
            for tool in function_tools:
                tool_name = tool.get("function", {}).get("name")
                if tool_name in tools_set:
                    available_tools.append(tool)
        except Exception as e:
            logger.warning(f"Function Call工具加载失败: error={e}")

        # 获取所有可用的MCP工具
        try:
            # 找出tools_set中包含的MCP服务器名称
            specified_mcp_servers_set = {server_name for server_name in mcp_server_names if server_name in tools_set}

            if specified_mcp_servers_set:
                # 如果配置中包含MCP服务器名称，则只加载指定服务器的工具
                mcp_tools = await get_mcp_list(list(specified_mcp_servers_set))
                available_tools.extend(mcp_tools)

            # 处理不是服务器名称的工具（按工具名称过滤）
            non_server_tools = tools_set - mcp_server_names
            if non_server_tools:
                # 从未加载过的服务器中获取工具列表，避免重复获取
                remaining_servers = list(mcp_server_names - specified_mcp_servers_set)
                if remaining_servers:
                    mcp_tools = await get_mcp_list(remaining_servers)
                    for tool in mcp_tools:
                        tool_name = tool.get("function", {}).get("name")
                        if tool_name in non_server_tools:
                            available_tools.append(tool)
        except Exception as e:
            logger.warning(f"MCP工具加载失败，仅使用Function Call工具: error={e}")

        return available_tools


# 全局工具加载器实例

_tool_loader = AgentToolLoader()


async def load_agent_tools(agent_name: str, tools_list: list[str] | None = None) -> list[dict]:
    """
    为Agent加载工具的通用函数

    Args:
        agent_name: Agent名称
        tools_list: 工具列表，默认为空列表，如果为None则从配置中获取

    Returns:
        工具列表
    """
    return await _tool_loader.load_agent_tools(agent_name, tools_list)
