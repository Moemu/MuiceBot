from abc import ABCMeta, abstractmethod
from importlib.util import find_spec
from typing import Any, AsyncGenerator, List, Literal, Optional, Union, overload

from pydantic import BaseModel, field_validator

from .._types import Message
from ..plugin import get_function_calls


class ModelConfig(BaseModel):
    loader: str = ""
    """所使用加载器的名称，位于 llm 文件夹下，loader 开头必须大写"""

    system_prompt: str = ""
    """系统提示"""
    auto_system_prompt: bool = False
    """是否自动配置沐雪的系统提示"""
    user_instructions: str = ""
    """用户提示"""
    auto_user_instructions: bool = False
    """是否自动配置沐雪的用户提示"""
    max_tokens: int = 4096
    """最大回复 Tokens """
    temperature: float = 0.75
    """模型的温度系数"""
    top_p: float = 0.95
    """模型的 top_p 系数"""
    top_k: float = 3
    """模型的 top_k 系数"""
    frequency_penalty: float = 1.0
    """模型的频率惩罚"""
    presence_penalty: float = 0.0
    """模型的存在惩罚"""
    repetition_penalty: float = 1.0
    """模型的重复惩罚"""
    think: Literal[0, 1, 2] = 1
    """针对 Deepseek-R1 等思考模型的思考过程提取模式"""
    stream: bool = False
    """是否使用流式输出"""
    online_search: bool = False
    """是否启用联网搜索（原生实现）"""

    model_path: str = ""
    """本地模型路径"""
    adapter_path: str = ""
    """基于 model_path 的微调模型或适配器路径"""
    template: str = ""
    """LLaMA-Factory 中模型的模板"""

    model_name: str = ""
    """所要使用模型的名称"""
    api_key: str = ""
    """在线服务的 API KEY"""
    api_secret: str = ""
    """在线服务的 api secret """
    api_host: str = ""
    """自定义 API 地址"""

    app_id: str = ""
    """xfyun 的 app_id"""
    service_id: str = ""
    """xfyun 的 service_id"""
    resource_id: str = ""
    """xfyun 的 resource_id"""

    multimodal: bool = False
    """是否为多模态模型（注意：对应的加载器必须实现 `ask_vision` 方法）"""

    @field_validator("loader")
    @classmethod
    def check_model_loader(cls, loader) -> str:
        if not loader:
            raise ValueError("loader is required")

        # Check if the specified loader exists
        module_path = f"muicebot.llm.{loader}"

        # 使用 find_spec 仅检测模块是否存在，不实际导入
        if find_spec(module_path) is None:
            raise ValueError(f"指定的模型加载器 '{loader}' 不存在于 llm 目录中")

        return loader


class BasicModel(metaclass=ABCMeta):
    def __init__(self, model_config: ModelConfig) -> None:
        """
        统一在此处声明变量
        """
        self.config = model_config
        self.is_running = False

    def _require(self, *require_fields: str):
        """
        通用校验方法：检查指定的配置项是否存在，不存在则抛出错误

        :param require_fields: 需要检查的字段名称（字符串）
        """
        missing_fields = [field for field in require_fields if not getattr(self.config, field, None)]
        if missing_fields:
            raise ValueError(f"对于 {self.config.loader} 以下配置是必需的: {', '.join(missing_fields)}")

    def _build_messages(self, prompt: str, history: List[Message]):
        """
        构建对话上下文历史的函数
        """
        pass

    def load(self) -> bool:
        """
        加载模型（通常是耗时操作，在线模型如无需校验可直接返回 true）

        :return: 是否加载成功
        """
        self.is_running = True
        return True

    @abstractmethod
    async def _ask_sync(self, messages: list, *args, **kwargs) -> str:
        """
        同步模型调用（子类必须实现）
        """
        pass

    def _ask_stream(self, messages: list, *args, **kwargs):
        """
        流式输出
        """
        pass

    @overload
    async def ask(
        self,
        prompt: str,
        history: List[Message],
        images: Optional[List[str]] = [],
        tools: Optional[List[dict]] = [],
        stream: Literal[False] = False,
        **kwargs,
    ) -> str: ...

    @overload
    async def ask(
        self,
        prompt: str,
        history: List[Message],
        images: Optional[List[str]] = [],
        tools: Optional[List[dict]] = [],
        stream: Literal[True] = True,
        **kwargs,
    ) -> AsyncGenerator[str, None]: ...

    @abstractmethod
    async def ask(
        self,
        prompt: str,
        history: List[Message],
        images: Optional[List[str]] = [],
        tools: Optional[List[dict]] = [],
        stream: Optional[bool] = False,
        **kwargs,
    ) -> Union[AsyncGenerator[str, None], str]:
        """
        模型交互询问

        :param prompt: 询问的内容
        :param history: 询问历史记录
        :param images: 本地图片路径列表
        :param tools: 工具列表
        :param stream: 是否使用流式输出

        :return: 模型回复
        """
        pass


class FunctionCallRequest(BaseModel):
    """
    模型 FunctionCall 请求
    """

    func: str
    """函数名称"""
    arguments: dict[str, str] | None = None
    """函数参数"""


async def function_call_handler(func: str, arguments: dict[str, str] | None = None) -> Any:
    """
    模型 Function Call 请求处理
    """
    arguments = arguments if arguments else {}
    func_caller = get_function_calls().get(func)
    return await func_caller.run(**arguments) if func_caller else "(Unknown Function)"
