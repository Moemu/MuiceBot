import importlib
import time
from typing import AsyncGenerator, Optional

from nonebot import logger

from ._types import Message
from .config import get_model_config
from .database import Database
from .llm import BasicModel
from .llm.utils.thought import process_thoughts, stream_process_thoughts
from .plugin import get_tools


class Muice:
    """
    Muice交互类
    """

    def __init__(self):
        self.model_config = get_model_config()
        self.think = self.model_config.think
        self.model_loader = self.model_config.loader
        self.multimodal = self.model_config.multimodal
        self.database = Database()
        self.__load_model()

    def __load_model(self) -> None:
        """
        初始化模型类
        """
        module_name = f"muicebot.llm.{self.model_loader}"
        module = importlib.import_module(module_name)
        ModelClass = getattr(module, self.model_loader, None)
        self.model: Optional[BasicModel] = ModelClass(self.model_config) if ModelClass else None

    def load_model(self) -> bool:
        """
        加载模型

        return: 是否加载成功
        """
        if not self.model:
            logger.error("模型加载失败: self.model 变量不存在")
            return False
        if not self.model.load():
            logger.error("模型加载失败: self.model.load 函数失败")
            return False
        return True

    def change_model_config(self, config_name: str) -> str:
        """
        更换模型配置文件并重新加载模型
        """
        try:
            self.model_config = get_model_config(config_name)
        except (ValueError, FileNotFoundError) as e:
            return str(e)
        self.think = self.model_config.think
        self.model_loader = self.model_config.loader
        self.multimodal = self.model_config.multimodal
        self.__load_model()
        self.load_model()

        return f"已成功加载 {config_name}" if config_name else "未指定模型配置名，已加载默认模型配置"

    async def ask(
        self,
        message: str,
        userid: str,
        image_paths: list = [],
        enable_history: bool = True,
    ) -> str:
        """
        调用模型

        :param message: 消息内容
        :param image_paths: 图片URL列表（仅在多模态启用时生效）
        :param user_id: 用户ID
        :param enable_history: 启用历史记录
        :return: 模型回复
        """
        if not (self.model and self.model.is_running):
            logger.error("模型未加载")
            return "(模型未加载)"

        logger.info("正在调用模型...")

        history = await self.database.get_history(userid) if enable_history else []

        start_time = time.perf_counter()
        logger.debug(f"模型调用参数：Prompt: {message}, History: {history}")

        reply = await self.model.ask(message, history, image_paths, stream=False, tools=get_tools())

        if isinstance(reply, str):
            reply.strip()
        end_time = time.perf_counter()
        logger.success(f"模型调用成功: {reply}")
        logger.debug(f"模型调用时长: {end_time - start_time} s")

        thought, result = process_thoughts(reply, self.think)  # type: ignore
        reply = "\n\n".join([thought, result])

        message_object = Message(userid=userid, message=message, respond=result, images=image_paths)

        await self.database.add_item(message_object)

        return reply

    async def ask_stream(
        self, message: str, userid: str, image_paths: list = [], enable_history: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        以流式方式调用模型并逐步返回输出
        """
        if not (self.model and self.model.is_running):
            logger.error("模型未加载")
            yield "(模型未加载)"
            return

        logger.info("正在调用模型...")

        history = await self.database.get_history(userid)

        start_time = time.perf_counter()
        logger.debug(f"模型调用参数：Prompt: {message}, History: {history}")

        response = await self.model.ask(message, history, image_paths, stream=True, tools=get_tools())

        reply = ""

        if isinstance(response, str):
            yield response.strip()
            reply = response
        else:
            async for chunk in response:
                yield (chunk if not self.think else stream_process_thoughts(chunk, self.think))  # type:ignore
                reply += chunk

        end_time = time.perf_counter()
        logger.success(f"已完成流式回复: {reply}")
        logger.debug(f"模型调用时长: {end_time - start_time} s")

        _, result = process_thoughts(reply, self.think)  # type: ignore

        message_object = Message(userid=userid, message=message, respond=result, images=image_paths)

        await self.database.add_item(message_object)

    async def refresh(self, userid: str) -> str:
        """
        刷新对话
        """
        logger.info(f"用户 {userid} 请求刷新")

        last_item = await self.database.get_history(userid, limit=1)
        last_item = last_item[0]

        if not last_item:
            logger.warning("用户对话数据不存在，拒绝刷新")
            return "你都还没和我说过一句话呢，得和我至少聊上一段才能刷新哦"
        if not (self.model and self.model.is_running):
            logger.error("模型未加载")
            return "(模型未加载)"

        userid = last_item.userid
        message = last_item.message
        image_paths = last_item.images

        await self.database.remove_last_item(userid)
        history = await self.database.get_history(userid)

        start_time = time.perf_counter()
        logger.debug(f"模型调用参数：Prompt: {message}, History: {history}")
        reply = await self.model.ask(
            message, history, image_paths, stream=False
        )  # TODO: 或许什么时候刷新操作支持流式，我想应该要复用 ask 了
        if isinstance(reply, str):
            reply.strip()
        end_time = time.perf_counter()

        logger.success(f"模型调用成功: {reply}")
        logger.debug(f"模型调用时长: {end_time - start_time} s")

        thought, result = process_thoughts(reply, self.think)  # type: ignore
        reply = "\n\n".join([thought, result])

        message_class = Message(userid=userid, message=message, respond=result, images=image_paths)

        await self.database.add_item(message_class)

        return reply

    async def reset(self, userid: str) -> str:
        """
        清空历史对话（将用户对话历史记录标记为不可用）
        """
        await self.database.mark_history_as_unavailable(userid)
        return "已成功移除对话历史~"

    async def undo(self, userid: str) -> str:
        await self.database.remove_last_item(userid)
        return "已成功撤销上一段对话~"
