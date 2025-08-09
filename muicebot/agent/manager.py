from .config import AgentConfigManager, AgentResponse
from .core import Agent


class AgentManager:
    """Agent管理器"""

    def __init__(self):
        self.config_manager = AgentConfigManager()
        self._agents: dict = {}

    async def dispatch_agent_task(
        self, agent_name: str, task: str, userid: str = "", is_private: bool = False
    ) -> AgentResponse:
        """分发任务给指定Agent"""
        from nonebot import logger

        logger.info(f"开始分发Agent任务: agent_name={agent_name}, task={task[:50]}..., userid={userid}")

        try:
            # 获取或创建Agent实例
            agent = self._get_or_create_agent(agent_name)
            logger.info(f"Agent实例获取/创建成功: {agent_name}")

            # 执行任务
            response = await agent.execute(task, userid, is_private)
            logger.info(f"Agent任务执行完成: {agent_name}, need_continue={response.need_continue}")

            return response
        except Exception as e:
            logger.error(f"Agent任务分发失败: {e}")
            return AgentResponse(result=f"任务分发失败: {str(e)}", need_continue=False)

    def _get_or_create_agent(self, agent_name: str) -> Agent:
        """获取或创建Agent实例"""
        from nonebot import logger

        if agent_name not in self._agents:
            logger.info(f"创建新的Agent实例: {agent_name}")
            try:
                config = self.config_manager.get_agent_config(agent_name)
                self._agents[agent_name] = Agent(config, agent_name)
                logger.info(f"Agent实例创建成功: {agent_name}")
            except Exception as e:
                logger.error(f"Agent实例创建失败: {agent_name}, 错误: {e}")
                raise

        logger.debug(f"使用Agent实例: {agent_name}")
        return self._agents[agent_name]

    async def handle_agent_response(self, response: AgentResponse) -> tuple[str, bool]:
        """处理Agent返回的结果"""
        from nonebot import logger

        # Agent只返回结果，不决定是否继续调用
        # 继续调用的决定权在muicebot
        logger.info("Agent响应处理完成，结果已返回")
        return response.result, False

    def reload_configs(self):
        """重新加载配置"""
        self.config_manager.reload_configs()
        # 清空已缓存的Agent实例，以便重新创建
        self._agents.clear()
