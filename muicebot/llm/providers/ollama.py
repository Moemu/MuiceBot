from typing import Any, AsyncGenerator, List, Literal, Optional, Union, overload

import ollama
from nonebot import logger
from ollama import ResponseError

from .. import (
    BaseLLM,
    ModelCompletions,
    ModelConfig,
    ModelRequest,
    ModelStreamCompletions,
    register,
)
from ..utils.images import get_file_base64
from ..utils.tools import function_call_handler


@register("ollama")
class Ollama(BaseLLM):
    """
    使用 Ollama 模型服务调用模型
    """

    def __init__(self, model_config: ModelConfig) -> None:
        super().__init__(model_config)
        self._require("model_name")
        self.model = self.config.model_name
        self.host = self.config.api_host if self.config.api_host else "http://localhost:11434"
        self.top_k = self.config.top_k
        self.top_p = self.config.top_p
        self.temperature = self.config.temperature
        self.repeat_penalty = self.config.repetition_penalty or 1
        self.presence_penalty = self.config.presence_penalty or 0
        self.frequency_penalty = self.config.frequency_penalty or 1
        self.stream = self.config.stream

    def load(self) -> bool:
        try:
            self.client = ollama.AsyncClient(host=self.host)
            self.is_running = True
        except ResponseError as e:
            logger.error(f"加载 Ollama 加载器时发生错误： {e}")
        except ConnectionError as e:
            logger.error(f"加载 Ollama 加载器时发生错误： {e}")
        finally:
            return self.is_running

    def __build_multi_messages(self, request: ModelRequest) -> dict:
        """
        构建多模态类型

        当前模型加载器支持的多模态类型: `image`
        """
        images = []

        for resource in request.resources:
            if resource.path is None:
                continue
            image_base64 = get_file_base64(local_path=resource.path)
            images.append(image_base64)

        message = {"role": "user", "content": request.prompt, "images": images}

        return message

    def _build_messages(self, request: ModelRequest) -> list:
        messages = []

        if request.system:
            messages.append({"role": "system", "content": request.system})

        for index, item in enumerate(request.history):
            messages.append(self.__build_multi_messages(ModelRequest(item.message, resources=item.resources)))
            messages.append({"role": "assistant", "content": item.respond})

        message = self.__build_multi_messages(request)

        messages.append(message)

        return messages

    async def _ask_sync(
        self,
        messages: list,
        tools: List[dict[str, Any]],
        response_format: Optional[dict[str, Any]],
        total_tokens: int = -1,
    ) -> ModelCompletions:
        completions = ModelCompletions()

        try:
            response = await self.client.chat(
                model=self.model,
                messages=messages,
                tools=tools,
                stream=False,
                format=response_format,
                options={
                    "temperature": self.temperature,
                    "top_k": self.top_k,
                    "top_p": self.top_p,
                    "repeat_penalty": self.repeat_penalty,
                    "presence_penalty": self.presence_penalty,
                    "frequency_penalty": self.frequency_penalty,
                },
            )

            tool_calls = response.message.tool_calls

            if not tool_calls:
                completions.text = response.message.content or "(警告：模型无返回)"
                return completions

            for tool in tool_calls:
                function_name = tool.function.name
                function_args = tool.function.arguments

                function_return = await function_call_handler(function_name, dict(function_args))

                messages.append(response.message)
                messages.append({"role": "tool", "content": str(function_return), "name": tool.function.name})
                return await self._ask_sync(messages, tools, response_format)

            completions.text = "模型调用错误：未知错误"
            completions.succeed = False
            return completions

        except ollama.ResponseError as e:
            error_info = f"模型调用错误: {e.error}"
            logger.error(error_info)
            completions.succeed = False
            completions.text = error_info
            return completions

    async def _ask_stream(
        self,
        messages: list,
        tools: List[dict[str, Any]],
        response_format: Optional[dict[str, Any]],
        total_tokens: int = -1,
    ) -> AsyncGenerator[ModelStreamCompletions, None]:
        try:
            response = await self.client.chat(
                model=self.model,
                messages=messages,
                tools=tools,
                stream=True,
                format=response_format,
                options={
                    "temperature": self.temperature,
                    "top_k": self.top_k,
                    "top_p": self.top_p,
                    "repeat_penalty": self.repeat_penalty,
                    "presence_penalty": self.presence_penalty,
                    "frequency_penalty": self.frequency_penalty,
                },
            )

            async for chunk in response:
                stream_completions = ModelStreamCompletions()

                tool_calls = chunk.message.tool_calls

                if chunk.message.content:
                    stream_completions.chunk = chunk.message.content
                    yield stream_completions
                    continue

                if not tool_calls:
                    continue

                for tool in tool_calls:  # type: ignore
                    function_name = tool.function.name
                    function_args = tool.function.arguments

                    function_return = await function_call_handler(function_name, dict(function_args))

                    messages.append(chunk.message)  # type: ignore
                    messages.append({"role": "tool", "content": str(function_return), "name": tool.function.name})

                    async for content in self._ask_stream(messages, tools, response_format):
                        yield content

        except ollama.ResponseError as e:
            stream_completions = ModelStreamCompletions()
            error_info = f"模型调用错误: {e.error}"
            logger.error(error_info)
            stream_completions.chunk = error_info
            stream_completions.succeed = False
            yield stream_completions
            return

    @overload
    async def ask(self, request: ModelRequest, *, stream: Literal[False] = False) -> ModelCompletions: ...

    @overload
    async def ask(
        self, request: ModelRequest, *, stream: Literal[True] = True
    ) -> AsyncGenerator[ModelStreamCompletions, None]: ...

    async def ask(
        self, request: ModelRequest, *, stream: bool = False
    ) -> Union[ModelCompletions, AsyncGenerator[ModelStreamCompletions, None]]:
        tools = request.tools if request.tools else []
        messages = self._build_messages(request)
        if request.format == "json" and request.json_schema:
            format = request.json_schema.model_json_schema()
        else:
            format = None

        if stream:
            return self._ask_stream(messages, tools, format)

        return await self._ask_sync(messages, tools, format)
