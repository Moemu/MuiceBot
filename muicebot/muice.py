import os
import time
from typing import AsyncGenerator, Optional, Union

from nonebot import logger
from nonebot_plugin_orm import async_scoped_session

from .agent import get_agent_list
from .agent.communication import AgentCommunication
from .config import (
    ModelConfig,
    get_model_config,
    get_model_config_manager,
    plugin_config,
)
from .database import MessageORM
from .llm import (
    MODEL_DEPENDENCY_MAP,
    ModelCompletions,
    ModelRequest,
    ModelStreamCompletions,
    get_missing_dependencies,
    load_model,
)
from .models import Message, Resource
from .plugin.func_call import get_function_list
from .plugin.hook import HookType, hook_manager
from .plugin.mcp import get_mcp_list
from .templates import generate_prompt_from_template
from .utils.utils import get_username


class Muice:
    """
    Muice交互类
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._model_config_manager = get_model_config_manager()

        self.model_config = self._model_config_manager.get_model_config()
        self.model_config_name = self._model_config_manager.get_name_from_config(self.model_config)

        self.database = MessageORM()
        self.max_history_epoch = plugin_config.max_history_epoch

        self.system_prompt = ""
        self.user_instructions = ""

        self._load_config()
        self._init_model()

        self._model_config_manager.register_listener(self._on_config_changed)

        # 初始化Agent通信接口
        self.agent_communication = AgentCommunication()

        self._initialized = True

    def __del__(self):
        # 注销监听器
        try:
            model_config_manager = get_model_config_manager()
            model_config_manager.unregister_listener(self._on_config_changed)
        except (AttributeError, RuntimeError) as e:
            logger.debug(f"Muice __del__ 清理失败: {e}")

    @staticmethod
    def get_instance() -> "Muice":
        return Muice()

    def _load_config(self):
        """
        加载配置项
        """
        self.model_provider = self.model_config.provider
        self.multimodal = self.model_config.multimodal
        self.template = self.model_config.template
        self.template_mode = self.model_config.template_mode

    def _init_model(self) -> None:
        """
        初始化模型类
        """
        try:
            self.model = load_model(self.model_config)

        except (ImportError, ModuleNotFoundError) as e:
            import sys

            logger.critical(f"导入模型加载器 '{self.model_provider}' 失败：{e}")
            dependencies = MODEL_DEPENDENCY_MAP.get(self.model_provider, [])
            missing = get_missing_dependencies(dependencies)
            if missing:
                install_command = "pip install " + " ".join(missing)
                logger.critical(f"缺少依赖库：{', '.join(missing)}\n请运行以下命令安装缺失项：\n\n{install_command}")
            sys.exit(1)

    def load_model(self) -> bool:
        """
        加载模型

        return: 是否加载成功
        """
        if not self.model.load():
            logger.error("模型加载失败: self.model.load 函数失败")
            return False

        return True

    def _on_config_changed(self, new_config: ModelConfig, old_config: Optional[ModelConfig] = None):
        """配置文件变更时的回调函数"""
        logger.info("检测到配置文件变更，自动重载模型...")
        # 更新配置
        old_config_name = self.model_config_name
        self.model_config = new_config
        self.model_config_name = self._model_config_manager.get_name_from_config(new_config)

        # 重新加载模型
        self._load_config()
        self._init_model()
        self.load_model()

        # 重新加载Agent配置
        self.agent_communication.reload_configs()

        logger.success(f"模型自动重载完成: {old_config_name} -> {self.model_config_name}")

    def change_model_config(self, config_name: Optional[str] = None, reload: bool = False) -> str:
        """
        更换模型配置文件并重新加载模型

        :param config_name: 模型配置名称
        :param reload: 是否处于重载状态（`config_name` 此时应该为空）

        :return: 切换状态提示
        """
        if reload and not config_name:
            config_name = self.model_config_name

        try:
            self.model_config = get_model_config(config_name)
            self.model_config_name = self._model_config_manager.get_name_from_config(self.model_config)
        except (ValueError, FileNotFoundError) as e:
            return str(e)

        self._load_config()
        self._init_model()
        self.load_model()

        if reload:
            return f"已成功重载模型配置文件: {config_name}"

        return f"已成功加载 {config_name}" if config_name else "未指定模型配置名，已加载默认模型配置"

    async def _prepare_prompt(self, message: str, userid: str, is_private: bool) -> str:
        """
        准备提示词(包含系统提示)

        :param message: 消息主体
        :param userid: 用户 Nonebot ID
        :param is_private: 是否为私聊信息
        :return: 最终模型提示词
        """
        if self.template is None:
            return message

        system_prompt = generate_prompt_from_template(self.template, userid, is_private).strip()

        if self.template_mode == "system":
            self.system_prompt = system_prompt
        else:
            self.user_instructions = system_prompt

        if is_private:
            return f"{self.user_instructions}\n\n{message}" if self.user_instructions else message

        group_prompt = f"<{await get_username()}> {message}"

        return f"{self.user_instructions}\n\n{group_prompt}" if self.user_instructions else group_prompt

    async def _prepare_history(
        self, session: async_scoped_session, userid: str, groupid: str = "-1", enable_history: bool = True
    ) -> list[Message]:
        """
        准备对话历史

        :param userid: 用户名
        :param groupid: 群组ID等(私聊时此值为-1)
        :param enable_history: 是否启用历史记录
        :return: 最终模型提示词
        """
        user_history = (
            await self.database.get_user_history(session, userid, self.max_history_epoch) if enable_history else []
        )

        # 验证多模态资源路径是否可用
        for item in user_history:
            item.resources = [
                resource for resource in item.resources if resource.path and os.path.isfile(resource.path)
            ]

        if groupid == "-1":
            return user_history[-self.max_history_epoch :]

        group_history = await self.database.get_group_history(session, groupid, self.max_history_epoch)

        for item in group_history:
            item.resources = [
                resource for resource in item.resources if resource.path and os.path.isfile(resource.path)
            ]

        # 群聊历史构建成 <Username> Message 的格式，避免上下文混乱
        for item in group_history:
            user_name = await get_username(item.userid)
            item.message = f"<{user_name}> {item.message}"

        final_history = list(set(user_history + group_history))

        return final_history[-self.max_history_epoch :]

    async def ask_with_agent_assistance(
        self,
        session: async_scoped_session,
        message: Message,
        enable_history: bool = True,
        enable_plugins: bool = True,
    ) -> ModelCompletions:
        """
        支持Agent协助的询问方法

        :param session: 数据库会话
        :param message: 消息文本
        :param enable_history: 是否启用历史记录
        :param enable_plugins: 是否启用工具插件
        :return: 模型回复
        """
        # 检查是否需要Agent协助
        if self._need_agent_assistance(message.message):
            agent_name, task = self._extract_agent_task(message.message)
            if agent_name and task:
                logger.info(f"检测到Agent协助请求: agent_name={agent_name}, task={task}")

                # 调用Agent获取结果
                agent_result = await self.agent_communication.request_agent_assistance(
                    agent_name, task, message.userid, message.groupid == "-1"
                )

                # 将Agent结果作为上下文继续对话
                message.message = f"基于以下信息回答用户问题:\n\n{agent_result}\n\n用户问题: {message.message}"
                logger.info(f"Agent协助处理完成，更新后的消息长度: {len(message.message)}")

        # 调用原有的ask方法，muicebot会根据工具提示词自行决定是否需要继续调用Agent
        return await self.ask(session, message, enable_history, enable_plugins)

    def _need_agent_assistance(self, message: str) -> bool:
        """判断是否需要Agent协助"""
        # 简单实现：检查消息中是否包含特定关键词
        # 实际实现中可以根据更复杂的规则来判断
        agent_keywords = ["@agent", "@助手", "请使用", "使用以下工具"]
        return any(keyword in message for keyword in agent_keywords)

    def _extract_agent_task(self, message: str) -> tuple[str, str]:
        """提取Agent名称和任务"""
        # 简单实现：根据特定格式提取
        # 实际实现中可以使用更复杂的解析逻辑
        if "@agent" in message:
            parts = message.split("@agent", 1)
            if len(parts) > 1:
                agent_part = parts[1].strip()
                if ":" in agent_part:
                    agent_name, task = agent_part.split(":", 1)
                    return agent_name.strip(), task.strip()
        elif "请使用" in message:
            parts = message.split("请使用", 1)
            if len(parts) > 1:
                agent_part = parts[1].strip()
                if " " in agent_part:
                    agent_name, task = agent_part.split(" ", 1)
                    return agent_name.strip(), task.strip()

        return "", message

    async def ask(
        self,
        session: async_scoped_session,
        message: Message,
        enable_history: bool = True,
        enable_plugins: bool = True,
    ) -> ModelCompletions:
        """
        调用模型

        :param message: 消息文本
        :param enable_history: 是否启用历史记录
        :param enable_plugins: 是否启用工具插件
        :return: 模型回复
        """
        if not (self.model and self.model.is_running):
            logger.error("模型未加载")
            return ModelCompletions("模型未加载", succeed=False)

        is_private = message.groupid == "-1"
        logger.info("正在调用模型...")

        await hook_manager.run(HookType.BEFORE_PRETREATMENT, message)

        prompt = await self._prepare_prompt(message.message, message.userid, is_private)
        history = (
            await self._prepare_history(session, message.userid, message.groupid, enable_history)
            if enable_history
            else []
        )
        tools = (
            (await get_function_list() + await get_mcp_list() + await get_agent_list())
            if self.model_config.function_call and enable_plugins
            else []
        )
        system = self.system_prompt if self.system_prompt else None
        resources = message.resources if self.model_config.multimodal else []

        model_request = ModelRequest(prompt, history, resources, tools, system)
        await hook_manager.run(HookType.BEFORE_MODEL_COMPLETION, model_request)

        start_time = time.perf_counter()
        logger.debug(f"模型调用参数：Prompt: {message}, History: {history}")

        response = await self.model.ask(model_request, stream=False)

        end_time = time.perf_counter()

        logger.success(f"模型调用{'成功' if response.succeed else '失败'}: {response}")
        logger.debug(f"模型调用时长: {end_time - start_time} s (token用量: {response.usage})")

        message.respond = response.text
        message.usage = response.usage

        if message.respond.strip() == "":
            msg = "模型回复为空，可能是模型未能正确处理请求，请检查模型配置或输入内容。"
            logger.warning(msg)
            return ModelCompletions(msg, succeed=False)

        await hook_manager.run(HookType.AFTER_MODEL_COMPLETION, response, message)

        await hook_manager.run(HookType.ON_FINISHING_CHAT, message)

        if response.succeed:
            await self.database.add_item(session, message)

        return response

    async def ask_stream_with_agent_assistance(
        self,
        session: async_scoped_session,
        message: Message,
        enable_history: bool = True,
        enable_plugins: bool = True,
    ) -> AsyncGenerator[ModelStreamCompletions, None]:
        """
        支持Agent协助的流式询问方法

        :param session: 数据库会话
        :param message: 消息文本
        :param enable_history: 是否启用历史记录
        :param enable_plugins: 是否启用工具插件
        :return: 模型回复
        """
        # 检查是否需要Agent协助
        if self._need_agent_assistance(message.message):
            agent_name, task = self._extract_agent_task(message.message)
            if agent_name and task:
                logger.info(f"检测到Agent协助请求(流式): agent_name={agent_name}, task={task}")

                # 调用Agent获取结果
                agent_result = await self.agent_communication.request_agent_assistance(
                    agent_name, task, message.userid, message.groupid == "-1"
                )

                # 将Agent结果作为上下文继续对话
                message.message = f"基于以下信息回答用户问题:\n\n{agent_result}\n\n用户问题: {message.message}"
                logger.info(f"Agent协助处理完成(流式)，更新后的消息长度: {len(message.message)}")

        # 调用原有的ask_stream方法，muicebot会根据工具提示词自行决定是否需要继续调用Agent
        async for chunk in self.ask_stream(session, message, enable_history, enable_plugins):
            yield chunk

    async def ask_stream(
        self,
        session: async_scoped_session,
        message: Message,
        enable_history: bool = True,
        enable_plugins: bool = True,
    ) -> AsyncGenerator[ModelStreamCompletions, None]:
        """
        调用模型

        :param message: 消息文本
        :param enable_history: 是否启用历史记录
        :param enable_plugins: 是否启用工具插件
        :return: 模型回复
        """
        if not (self.model and self.model.is_running):
            logger.error("模型未加载")
            yield ModelStreamCompletions("模型未加载")
            return

        is_private = message.groupid == "-1"
        logger.info("正在调用模型...")

        await hook_manager.run(HookType.BEFORE_PRETREATMENT, message)

        prompt = await self._prepare_prompt(message.message, message.userid, is_private)
        history = (
            await self._prepare_history(session, message.userid, message.groupid, enable_history)
            if enable_history
            else []
        )
        tools = (
            (await get_function_list() + await get_mcp_list() + await get_agent_list())
            if self.model_config.function_call and enable_plugins
            else []
        )
        system = self.system_prompt if self.system_prompt else None
        resources = message.resources if self.model_config.multimodal else []

        model_request = ModelRequest(prompt, history, resources, tools, system)
        await hook_manager.run(HookType.BEFORE_MODEL_COMPLETION, model_request)

        start_time = time.perf_counter()
        logger.debug(f"模型调用参数：Prompt: {message}, History: {history}")

        response = await self.model.ask(model_request, stream=True)

        total_reply = ""
        total_resources: list[Resource] = []
        item: Optional[ModelStreamCompletions] = None

        async for item in response:
            await hook_manager.run(HookType.ON_STREAM_CHUNK, item)
            total_reply += item.chunk
            yield item
            if item.resources:
                total_resources.extend(item.resources)

        if total_reply.strip() and not total_reply.endswith("\n\n"):
            yield ModelStreamCompletions("\n\n")  # 强行 yield 最后一段文字

        if item is None:
            raise RuntimeError("模型调用器返回的值应至少包含一个元素")

        end_time = time.perf_counter()
        logger.success(f"已完成流式回复: {total_reply}")
        logger.debug(f"模型调用时长: {end_time - start_time} s (token用量: {item.usage})")

        final_model_completions = ModelCompletions(
            text=total_reply, usage=item.usage, resources=total_resources.copy(), succeed=item.succeed
        )

        message.respond = total_reply
        message.usage = item.usage

        if total_reply.strip() == "":
            msg = "模型回复为空，可能是模型未能正确处理请求，请检查模型配置或输入内容。"
            logger.warning(msg)
            yield ModelStreamCompletions(msg, succeed=False)
            return

        await hook_manager.run(HookType.AFTER_MODEL_COMPLETION, final_model_completions, message, stream=True)

        # 提取挂钩函数的可能的 resources 资源
        new_resources = [r for r in final_model_completions.resources if r not in total_resources]

        # yield 新资源
        for r in new_resources:
            yield ModelStreamCompletions(resources=[r])

        await hook_manager.run(HookType.ON_FINISHING_CHAT, message)

        if item.succeed:
            await self.database.add_item(session, message)

    async def refresh(
        self, userid: str, session: async_scoped_session
    ) -> Union[AsyncGenerator[ModelStreamCompletions, None], ModelCompletions]:
        """
        刷新对话

        :userid: 用户唯一标识id
        """
        logger.info(f"用户 {userid} 请求刷新")

        user_history = await self.database.get_user_history(session, userid, limit=1)

        if not user_history:
            logger.warning("用户对话数据不存在，拒绝刷新")
            return ModelCompletions("你都还没和我说过一句话呢，得和我至少聊上一段才能刷新哦")

        last_item = user_history[0]

        await self.database.mark_history_as_unavailable(session, userid, 1)

        if not self.model_config.stream:
            return await self.ask(session, last_item)

        return self.ask_stream(session, last_item)

    async def reset(self, userid: str, session: async_scoped_session) -> str:
        """
        清空历史对话（将用户对话历史记录标记为不可用）
        """
        await self.database.mark_history_as_unavailable(session, userid)
        return "已成功移除对话历史~"

    async def undo(self, userid: str, session: async_scoped_session) -> str:
        await self.database.mark_history_as_unavailable(session, userid, 1)
        return "已成功撤销上一段对话~"
