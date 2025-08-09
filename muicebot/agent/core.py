from typing import List, Optional

from ..llm import ModelRequest, load_model
from ..plugin.func_call import get_function_calls
from ..plugin.mcp import get_mcp_list
from ..templates import generate_prompt_from_template
from .config import AgentConfig, AgentResponse, format_agent_output


class Agent:
    """Agent核心类"""

    def __init__(self, config: AgentConfig, agent_name: str = ""):
        self.config = config
        self.agent_name = agent_name or getattr(config, "name", "Agent")
        # 使用现有的load_model函数加载模型
        self.model = load_model(config)
        self.tools: List[dict] = []  # 初始化为空列表，工具将在需要时异步加载
        # Agent不再直接管理调用计数，由TaskChain管理

    async def _load_tools(self, tools_list: Optional[List[str]]) -> List[dict]:
        """加载Agent可调用的工具"""
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

    async def execute(self, task: str, userid: str = "", is_private: bool = False) -> AgentResponse:
        """执行任务"""
        from nonebot import logger

        logger.info(f"Agent开始执行任务: task={task[:50]}..., userid={userid}, is_private={is_private}")
        logger.info(f"Agent配置: function_call={self.config.function_call}, tools_list={self.config.tools_list}")

        # Agent不再直接处理循环调用逻辑，这些由TaskChain处理

        # 准备提示词和工具列表
        prompt = self._prepare_prompt(task, userid, is_private)
        tools = await self._prepare_tools()

        logger.debug(f"Agent提示词准备完成: prompt长度={len(prompt)}")
        logger.debug(f"Agent工具准备完成: 工具数量={len(tools)}")

        # 构造模型请求
        model_request = ModelRequest(prompt=prompt, tools=tools if self.config.function_call else [])

        logger.info("Agent模型请求构造完成，开始调用模型")

        # 调用模型
        try:
            response = await self.model.ask(model_request)
            logger.info(f"Agent模型调用完成: succeed={response.succeed}, 响应长度={len(response.text)}")
            logger.debug(f"Agent模型响应内容: {response.text[:200]}...")
        except Exception as e:
            logger.error(f"Agent模型调用失败: {e}")
            return AgentResponse(result=f"模型调用失败: {str(e)}", need_continue=False)

        # 解析响应并构造AgentResponse
        try:
            agent_response = self._parse_response(response)
            logger.info(
                f"Agent响应解析完成: result长度={len(agent_response.result)}, need_continue={agent_response.need_continue}"
            )
            if agent_response.need_continue:
                logger.info(
                    f"Agent请求继续调用: next_agent={agent_response.next_agent}, next_task={agent_response.next_task}"
                )
            return agent_response
        except Exception as e:
            logger.error(f"Agent响应解析失败: {e}")
            return AgentResponse(result=f"响应解析失败: {str(e)}", need_continue=False)

    def _prepare_prompt(self, task: str, userid: str, is_private: bool) -> str:
        """准备提示词"""
        if self.config.template:
            system_prompt = generate_prompt_from_template(self.config.template, userid, is_private).strip()
            return f"{system_prompt}\n\n{task}"
        return task

    async def _prepare_tools(self) -> List[dict]:
        """准备工具列表"""
        # 如果工具列表为空，则异步加载工具
        if not self.tools:
            self.tools = await self._load_tools(self.config.tools_list)
        return self.tools

    def _parse_response(self, model_response) -> AgentResponse:
        """解析模型响应"""
        from nonebot import logger

        result = model_response.text
        logger.debug(f"Agent响应解析完成: 结果长度={len(result)}")

        # 尝试从模型响应中提取是否需要继续调用的信息
        need_continue = False
        next_agent = None
        next_task = None

        # 简单的解析逻辑，实际实现中可以根据更复杂的规则来判断
        # 这里只是一个示例，实际应用中可能需要更复杂的解析逻辑
        if "需要继续" in result or "继续调用" in result:
            need_continue = True
            # 这里可以添加更复杂的逻辑来提取next_agent和next_task
            # 例如通过正则表达式或其他解析方法

        # 使用格式化函数包装Agent输出，确保主模型能正确识别和利用
        formatted_result = format_agent_output(self.agent_name, result, need_continue, next_agent, next_task)
        logger.debug(f"Agent输出格式化完成: 格式化后长度={len(formatted_result)}")

        return AgentResponse(
            result=formatted_result, need_continue=need_continue, next_agent=next_agent, next_task=next_task
        )
