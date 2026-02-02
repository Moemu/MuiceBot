"""
机器人框架中处理函数调用的模块。
该模块提供了一个系统，用于注册可被AI系统调用的函数，
具有自动依赖注入和参数验证功能。
它包括：
- Caller类：管理函数注册、依赖注入和执行
- 用于函数调用的注册装饰器
- 用于获取已注册函数调用的实用函数
"""

import inspect
from typing import Any, Optional, Type, get_type_hints

from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot.rule import Rule
from nonebot.typing import T_State
from pydantic import BaseModel
from typing_extensions import deprecated

from ..context import get_bot, get_event, get_mather
from ..utils import is_coroutine_callable
from ._types import ASYNC_FUNCTION_CALL_FUNC, F
from .parameter import FunctionCallJsonSchema, Parameter
from .utils import async_wrap

_caller_data: dict[str, "Caller"] = {}
"""函数注册表，存储所有注册的函数"""


class Caller:
    def __init__(self, description: str, params: Optional[Type[BaseModel]] = None, rule: Optional[Rule] = None):
        self._name: str = ""
        """函数名称"""
        self._description: str = description
        """函数描述"""
        self._rule: Optional[Rule] = rule
        """启用规则"""
        self._parameters: dict[str, Parameter] = {}
        """函数参数字典"""
        self._parameters_model: Optional[Type[BaseModel]] = params
        """函数参数 pydantic 模型"""
        self.function: ASYNC_FUNCTION_CALL_FUNC
        """函数对象"""
        self.default: dict[str, Any] = {}
        """默认值"""

        self.module_name: str = ""
        """函数所在模块名称"""

    def __call__(self, func: F) -> F:
        """
        修饰器：注册一个 Function_call 函数
        """
        # 确保为异步函数
        if is_coroutine_callable(func):
            self.function = func  # type: ignore
        else:
            self.function = async_wrap(func)  # type: ignore

        self._name = func.__name__

        # 获取模块名
        if module := inspect.getmodule(func):
            module_name = module.__name__.split(".")[-1]
        else:
            module_name = ""
        self.module_name = module_name

        _caller_data[self._name] = self
        logger.debug(f"Function Call 函数 {self.module_name}.{self._name} 已成功加载")
        return func

    async def _inject_dependencies(self, kwargs: dict) -> dict:
        """
        自动解析参数并进行依赖注入
        """
        sig = inspect.signature(self.function)
        hints = get_type_hints(self.function)

        inject_args = kwargs.copy()

        for name, param in sig.parameters.items():
            param_type = hints.get(name, None)

            if param_type and isinstance(param_type, type):
                if issubclass(param_type, Bot):
                    inject_args[name] = get_bot()

                elif issubclass(param_type, Event):
                    inject_args[name] = get_event()

                elif issubclass(param_type, Matcher):
                    inject_args[name] = get_mather()

                elif param_type.__name__ == "Muice":  # Check by type name
                    from muicebot.muice import Muice

                    inject_args[name] = Muice.get_instance()

                # elif param_type and issubclass(param_type, T_State):
                #     inject_args[name] = get_state()

            # 填充默认值
            elif param.default != inspect.Parameter.empty:
                inject_args[name] = kwargs.get(name, param.default)

            # 如果参数未提供，则检查是否有默认值
            elif name not in inject_args:
                raise ValueError(f"缺少必要参数: {name}")

        return inject_args

    @deprecated("由于此方法缺乏灵活性，请改用 `on_function_call` 中的 params 参数并传入 pydantic 模型")
    def params(self, **kwargs: Parameter) -> "Caller":
        self._parameters.update(kwargs)
        return self

    async def run(self, **kwargs) -> Any:
        """
        执行 function call
        """
        if self.function is None:
            raise ValueError("未注册函数对象")

        inject_args = await self._inject_dependencies(kwargs)

        return await self.function(**inject_args)

    def data(self) -> dict[str, Any]:
        """
        生成函数描述信息

        Note:
            如果通过 `_parameters_model` 提供了 pydantic 模型，则该模型优先于动态添加的 `_parameters`。
            这意味着参数验证和注入将根据 pydantic 模型来处理，而通过 `params()` 方法添加的任何参数都将被忽略。
            使用 `_parameters_model` 可以获得更强大和类型安全的参数验证。

        :return: 可用于 Function_call 的字典
        """
        if self._parameters_model:
            return {
                "type": "function",
                "function": {
                    "name": self._name,
                    "description": self._description,
                    "parameters": self._parameters_model.model_json_schema(schema_generator=FunctionCallJsonSchema),
                },
            }

        if not self._parameters:
            properties = {
                "dummy_param": {"type": "string", "description": "为了兼容性设置的一个虚拟参数，因此不需要填写任何值"}
            }
            required = []
        else:
            properties = {key: value.data() for key, value in self._parameters.items()}
            required = [key for key, value in self._parameters.items() if value.default is None]

        return {
            "type": "function",
            "function": {
                "name": self._name,
                "description": self._description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


def on_function_call(description: str, params: Optional[Type[BaseModel]] = None, rule: Optional[Rule] = None) -> Caller:
    """
    返回一个Caller类，可用于装饰一个函数，使其注册为一个可被AI调用的function call函数

    :param description: 函数描述，若为None则从函数的docstring中获取
    :param rule: 启用规则。不满足规则则不启用此 function call

    :return: Caller对象
    """
    caller = Caller(description=description, params=params, rule=rule)
    return caller


def get_function_calls() -> dict[str, Caller]:
    """获取所有已注册的function call函数

    Returns:
        dict[str, Caller]: 所有已注册的function call类
    """
    return _caller_data


async def get_function_list() -> list[dict[str, dict]]:
    """
    获取所有已注册的function call函数，并转换为工具格式

    :return: 所有已注册的function call函数列表
    """
    tools: list[dict[str, dict]] = []
    bot: Bot = get_bot()
    event: Event = get_event()
    state: T_State = {}

    for name, caller in _caller_data.items():
        if caller._rule is None or await caller._rule(bot, event, state):
            tools.append(caller.data())

    return tools
