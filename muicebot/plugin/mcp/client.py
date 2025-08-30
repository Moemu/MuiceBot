import asyncio
from typing import Any, Optional

from nonebot import logger

from .config import get_mcp_server_config
from .server import Server, Tool

_servers: list[Server] = list()


async def initialize_servers() -> None:
    """
    初始化全部 MCP 实例
    """
    server_config = get_mcp_server_config()
    _servers.extend([Server(name, srv_config) for name, srv_config in server_config.items()])
    for server in _servers:
        logger.info(f"初始化 MCP Server: {server.name}")
        try:
            await server.initialize()
        except Exception as e:
            logger.error(f"初始化 MCP Server 实例时出现问题: {e}")
            await cleanup_servers()
            raise


async def handle_mcp_tool(tool: str, arguments: Optional[dict[str, Any]] = None) -> Optional[str]:
    """
    处理 MCP Tool 调用
    """
    logger.info(f"执行 MCP 工具: {tool} (参数: {arguments})")

    for server in _servers:
        server_tools = await server.list_tools()
        if not any(server_tool.name == tool for server_tool in server_tools):
            continue

        try:
            result = await server.execute_tool(tool, arguments)

            if isinstance(result, dict) and "progress" in result:
                progress = result["progress"]
                total = result["total"]
                percentage = (progress / total) * 100
                logger.info(f"工具执行进度: {progress}/{total} ({percentage:.1f}%)")

            return f"Tool execution result: {result}"
        except Exception as e:
            error_msg = f"Error executing tool: {str(e)}"
            logger.error(error_msg)
            return error_msg

    return None  # Not found.


async def cleanup_servers() -> None:
    """
    清理 MCP 实例
    """
    cleanup_tasks = [asyncio.create_task(server.cleanup()) for server in _servers]
    if cleanup_tasks:
        try:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        except Exception as e:
            logger.warning(f"清理 MCP 实例时出现错误: {e}")


async def transform_json(tool: Tool) -> dict[str, Any]:
    """
    将 MCP Tool 转换为 OpenAI 所需的 parameters 格式，并删除多余字段
    """
    func_desc = {"name": tool.name, "description": tool.description, "parameters": {}, "required": []}

    if tool.input_schema:
        parameters = {
            "type": tool.input_schema.get("type", "object"),
            "properties": tool.input_schema.get("properties", {}),
            "required": tool.input_schema.get("required", []),
        }
        func_desc["parameters"] = parameters

    output = {"type": "function", "function": func_desc}

    return output


async def get_mcp_list(server_names: Optional[list[str]] = None) -> list[dict[str, dict]]:
    """
    获得适用于 OpenAI Tool Call 输入格式的 MCP 工具列表

    Args:
        server_names: 服务器名称列表，默认为 None，表示获取所有服务器的工具
    """
    all_tools: list[dict[str, dict]] = []
    target_servers = (
        [server for server in _servers if server.name in server_names] if server_names is not None else _servers
    )

    for server in target_servers:
        tools = await server.list_tools()
        all_tools.extend([await transform_json(tool) for tool in tools])

    return all_tools
