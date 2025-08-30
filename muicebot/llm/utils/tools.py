from typing import Any

from nonebot import logger
from nonebot_plugin_alconna import get_message_id

from muicebot.agent.utils import call_agent, is_agent
from muicebot.plugin.context import get_bot, get_event
from muicebot.plugin.func_call import get_function_calls
from muicebot.plugin.mcp import handle_mcp_tool


def get_current_message_id() -> str | None:
    """
    获取当前消息ID
    """
    try:
        bot = get_bot()
        event = get_event()
        return get_message_id(event, bot)
    except Exception as e:
        logger.warning(f"获取当前消息ID时出错: {e}")
        return None


async def function_call_handler(func: str, arguments: dict[str, str] | None = None) -> Any:
    """
    模型 Function Call 请求处理
    """
    arguments = arguments if arguments and arguments != {"dummy_param": ""} else {}

    if func_caller := get_function_calls().get(func):
        logger.info(f"Function call 请求 {func}, 参数: {arguments}")
        result = await func_caller.run(**arguments)
        logger.success(f"Function call 成功，返回: {result}")
        return result

    if is_agent(func):
        message_id = get_current_message_id()
        result = await call_agent(func, arguments, message_id)
        return result

    if mcp_result := await handle_mcp_tool(func, arguments):
        logger.success(f"MCP 工具执行成功，返回: {mcp_result}")
        return mcp_result

    return "(Unknown Function)"
