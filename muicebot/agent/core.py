from nonebot import logger

from muicebot.agent.config import AgentConfig, AgentResponse, format_agent_output
from muicebot.agent.tools import load_agent_tools
from muicebot.llm import ModelCompletions, ModelRequest, load_model
from muicebot.templates import generate_prompt_from_template


class Agent:
    """Agent核心类"""

    def __init__(self, config: AgentConfig, agent_name: str = ""):
        self.config = config
        self.agent_name = agent_name or "Agent"
        self.model = load_model(config.model_config_obj)
        self.tools: list[dict] | None = None

    async def _load_tools(self, tools_list: list[str] | None) -> list[dict]:
        """加载Agent可调用的工具 - 使用通用工具加载函数"""
        return await load_agent_tools(self.agent_name, tools_list)

    async def execute(self, task: str) -> AgentResponse:
        """执行任务"""
        logger.info(f"Agent开始执行任务: task={task[:50]}...")
        logger.info(
            f"Agent配置: function_call={self.config.model_config_obj.function_call}, "
            f"tools_list={self.config.tools_list}"
        )

        # 准备提示词和工具列表
        prompt = self._prepare_prompt(task, "Muice", True)

        # 如果工具列表尚未加载，则加载工具列表
        if self.tools is None:
            self.tools = await self._load_tools(self.config.tools_list)
        tools = self.tools

        logger.debug(f"Agent提示词准备完成: prompt长度={len(prompt)}")
        logger.debug(f"Agent工具准备完成: 工具数量={len(tools)}")

        # 构造模型请求
        model_request = ModelRequest(prompt=prompt, tools=tools)

        logger.info("Agent模型请求构造完成，开始调用模型")

        # 调用模型
        try:
            response = await self.model.ask(model_request)
            logger.info(f"Agent模型调用完成: succeed={response.succeed}, 响应长度={len(response.text)}")
            logger.debug(f"Agent模型响应内容: {response.text[:200]}...")

            # 检查模型调用是否成功
            if not response.succeed:
                logger.error(f"LLM内部错误: {response.text}")
                return AgentResponse(result=f"LLM内部错误: {response.text}")

        except Exception as e:
            logger.error(f"Agent模型调用失败: {e}")
            return AgentResponse(result=f"模型调用失败: {str(e)}")

        # 解析响应并构造AgentResponse
        try:
            agent_response = self._parse_response(response)
            logger.info(f"Agent响应解析完成: result长度={len(agent_response.result)}")
            return agent_response
        except Exception as e:
            logger.error(f"Agent响应解析失败: {e}")
            return AgentResponse(result=f"响应解析失败: {str(e)}")

    def _prepare_prompt(self, task: str, userid: str = "Muice", is_private: bool = True) -> str:
        """准备提示词"""
        if self.config.model_config_obj.template:
            # 使用传入的参数处理模板
            system_prompt = generate_prompt_from_template(
                self.config.model_config_obj.template, userid, is_private
            ).strip()
            return f"{system_prompt}\n\n{task}"
        return task

    def _parse_response(self, model_response: ModelCompletions) -> AgentResponse:
        """解析模型响应"""

        # 检查是否为错误响应
        if not model_response.succeed:
            logger.error(f"LLM响应错误: {model_response.text}")
            # 对于错误响应，直接返回错误信息，不进行格式化
            return AgentResponse(result=f"LLM错误: {model_response.text}")

        result = model_response.text
        logger.debug(f"Agent响应解析完成: 结果长度={len(result)}")

        # 使用格式化函数包装Agent输出，确保主模型能正确识别和利用
        formatted_result = format_agent_output(self.agent_name, result)
        logger.debug(f"Agent输出格式化完成: 格式化后长度={len(formatted_result)}")

        return AgentResponse(result=formatted_result)
