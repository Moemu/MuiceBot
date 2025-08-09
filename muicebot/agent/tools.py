from typing import Any, Optional

from ..plugin.func_call import get_function_calls
from ..plugin.mcp import handle_mcp_tool


async def agent_function_call_handler(func: str, arguments: Optional[dict] = None) -> Any:
    """处理Agent的工具调用"""
    # 尝试调用Function Call工具
    function_calls = get_function_calls()
    if func in function_calls:
        caller = function_calls[func]
        return await caller.run(**(arguments or {}))

    # 尝试调用MCP工具
    try:
        mcp_result = await handle_mcp_tool(func, arguments)
        if mcp_result:
            return mcp_result
    except Exception as e:
        from nonebot import logger

        logger.warning(f"MCP工具调用失败: func={func}, error={e}")

    # 工具未找到
    return f"未知工具: {func}"
