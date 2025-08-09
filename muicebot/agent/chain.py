import asyncio
import time
from typing import List, Optional

from .config import AgentConfig, AgentResponse


class TaskChain:
    """任务链管理"""

    def __init__(self, max_loops: Optional[int] = None):
        # 如果没有指定max_loops，则从Agent配置中获取默认值
        if max_loops is None:
            self.max_loops = AgentConfig.get_default_max_loop_count()
        else:
            self.max_loops = max_loops

        self.current_loop = 0
        self.history: List[AgentResponse] = []
        self.call_count = 0  # 调用计数器
        self.last_call_time = 0.0  # 上次调用时间

    def add_response(self, response: AgentResponse):
        """添加响应到历史记录"""
        self.history.append(response)

    def should_continue(self) -> bool:
        """判断是否应该继续任务链"""
        if self.current_loop >= self.max_loops:
            return False

        # 如果是第一次调用且没有历史记录，应该继续执行
        if not self.history:
            return True

        last_response = self.history[-1]
        return last_response.need_continue

    def get_next_task(self) -> Optional[tuple[str, str]]:
        """获取下一个任务"""
        if not self.history:
            return None

        last_response = self.history[-1]
        if last_response.need_continue and last_response.next_agent and last_response.next_task:
            return (last_response.next_agent, last_response.next_task)

        return None

    def increment_loop(self):
        """增加循环计数"""
        self.current_loop += 1

    def increment_call_count(self):
        """增加调用计数"""
        self.call_count += 1

    def check_loop_limit(self) -> tuple[bool, str]:
        """
        检查是否超过循环限制

        Returns:
            tuple[bool, str]: (是否超过限制, 限制信息)
        """
        if self.call_count > self.max_loops:
            return True, f"调用次数已达到最大限制 {self.max_loops}，无法继续调用"
        return False, ""

    async def wait_api_interval(self):
        """
        在调用之间添加API调用间隔
        """
        if self.call_count > 1:  # 第一次调用不需要等待
            current_time = time.time()
            time_since_last_call = current_time - self.last_call_time
            api_call_interval = AgentConfig.get_default_api_call_interval()
            if time_since_last_call < api_call_interval:
                wait_time = api_call_interval - time_since_last_call
                await asyncio.sleep(wait_time)
            self.last_call_time = time.time()
        else:
            self.last_call_time = time.time()

    def reset(self):
        """重置任务链"""
        self.current_loop = 0
        self.history.clear()

    def get_final_result(self) -> str:
        """获取最终结果"""
        if self.history:
            return self.history[-1].result
        return ""
