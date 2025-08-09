from typing import Any

from nonebot import logger

from muicebot.agent.communication import AgentCommunication
from muicebot.plugin.func_call import get_function_calls
from muicebot.plugin.mcp import handle_mcp_tool


async def function_call_handler(func: str, arguments: dict[str, str] | None = None) -> Any:
    """
    模型 Function Call 请求处理
    """
    arguments = arguments if arguments and arguments != {"dummy_param": ""} else {}

    # 检查是否为Agent工具调用
    if func.startswith("agent_"):
        agent_name = func[6:]  # 移除"agent_"前缀
        task = arguments.get("task", "") if arguments else ""
        if agent_name and task:
            # 调用Agent处理任务
            agent_comm = AgentCommunication()
            result = await agent_comm.request_agent_assistance(agent_name, task)
            logger.success(f"Agent {agent_name} 执行成功，返回: {result}")
            return result

    if func_caller := get_function_calls().get(func):
        logger.info(f"Function call 请求 {func}, 参数: {arguments}")
        result = await func_caller.run(**arguments)
        logger.success(f"Function call 成功，返回: {result}")
        return result

    if mcp_result := await handle_mcp_tool(func, arguments):
        logger.success(f"MCP 工具执行成功，返回: {mcp_result}")
        return mcp_result

    return "(Unknown Function)"
