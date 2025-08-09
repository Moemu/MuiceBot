from nonebot import logger

from .chain import TaskChain
from .manager import AgentManager


class AgentCommunication:
    """Agent与主模型通信接口"""

    def __init__(self):
        self.agent_manager = AgentManager()
        self.task_chain = TaskChain()

    async def request_agent_assistance(
        self, agent_name: str, task: str, userid: str = "", is_private: bool = False
    ) -> str:
        """请求Agent协助"""
        try:
            logger.info(
                f"开始请求Agent协助: agent_name={agent_name}, task={task}, userid={userid}, is_private={is_private}"
            )

            # 增加调用计数
            self.task_chain.increment_call_count()

            # 检查是否超过任务链的最大循环次数
            is_limited, limit_info = self.task_chain.check_loop_limit()
            if is_limited:
                logger.warning(f"任务链{limit_info}")
                return f"任务链{limit_info}。请重新开始新的任务。"

            # 等待API调用间隔
            await self.task_chain.wait_api_interval()

            # 调用Agent执行任务
            try:
                response = await self.agent_manager.dispatch_agent_task(agent_name, task, userid, is_private)
                self.task_chain.add_response(response)
                self.task_chain.increment_loop()
                result, continue_chain = await self.agent_manager.handle_agent_response(response)
                logger.info(f"Agent调用完成: result长度={len(result)}")
            except Exception as e:
                logger.error(f"Agent调用失败: {e}")
                return f"Agent调用失败: {str(e)}"
            logger.info("Agent协助请求完成")
            return result

        except Exception as e:
            logger.error(f"Agent协助请求发生未预期错误: {e}")
            return f"Agent调用失败: {str(e)}"

    def reload_configs(self):
        """重新加载配置"""
        try:
            logger.info("重新加载Agent配置")
            self.agent_manager.reload_configs()
            # 重置任务链
            self.task_chain.reset()
            logger.info("Agent配置重新加载完成")
        except Exception as e:
            logger.error(f"重新加载Agent配置失败: {e}")
