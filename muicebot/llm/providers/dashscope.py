import asyncio
import json
from dataclasses import dataclass
from functools import partial
from typing import AsyncGenerator, Generator, List, Literal, Optional, Union, overload

import dashscope
from dashscope.api_entities.dashscope_response import (
    GenerationResponse,
    MultiModalConversationResponse,
)
from nonebot import logger

from .. import (
    BaseLLM,
    ModelCompletions,
    ModelConfig,
    ModelRequest,
    ModelStreamCompletions,
    register,
)
from ..utils.tools import function_call_handler


@dataclass
class FunctionCallStream:
    enable: bool = False
    id: str = ""
    function_name: str = ""
    function_args: str = ""

    def from_chunk(self, chunk: GenerationResponse | MultiModalConversationResponse):
        tool_calls = chunk.output.choices[0].message.tool_calls
        tool_call = tool_calls[0]

        if tool_call.get("id", ""):
            self.id = tool_call["id"]

        if tool_call.get("function", {}).get("name", ""):
            self.function_name = tool_call.get("function").get("name")

        function_arg = tool_call.get("function", {}).get("arguments", "")

        if function_arg and self.function_args != function_arg:
            self.function_args += function_arg

        self.enable = True


class ThoughtStream:
    def __init__(self):
        self.is_insert_think_label: bool = False

    def process_chunk(self, chunk: GenerationResponse | MultiModalConversationResponse) -> str:
        choice = chunk.output.choices[0].message
        answer_content = choice.content
        reasoning_content = choice.get("reasoning_content", "")
        reasoning_content = reasoning_content.replace("\n</think>", "") if reasoning_content else ""

        # 处理模型可能输出的 reasoning（思考内容）
        if reasoning_content:
            if not self.is_insert_think_label:
                self.is_insert_think_label = True
                return f"<think>{reasoning_content}"
            else:
                return reasoning_content

        if not answer_content:
            answer_content = ""

        if isinstance(answer_content, list):
            answer_content = answer_content[0].get("text", "")

        if self.is_insert_think_label:
            self.is_insert_think_label = False
            return f"</think>{answer_content}"

        return answer_content


@register("dashscope")
class Dashscope(BaseLLM):
    def __init__(self, model_config: ModelConfig) -> None:
        super().__init__(model_config)
        self._require("api_key", "model_name")
        self.api_key = self.config.api_key
        self.model = self.config.model_name
        self.max_tokens = self.config.max_tokens
        self.temperature = self.config.temperature
        self.top_p = self.config.top_p
        self.repetition_penalty = self.config.repetition_penalty
        self.enable_search = self.config.online_search
        self.enable_thinking = self.config.enable_thinking
        self.thinking_budget = self.config.thinking_budget

        self.extra_headers = (
            {"X-DashScope-DataInspection": '{"input":"cip","output":"cip"}'} if self.config.content_security else {}
        )

        self.stream = False

    def __build_multi_messages(self, request: ModelRequest) -> dict:
        """
        构建多模态类型

        此模型加载器支持的多模态类型: `audio` `image`
        """
        multi_contents: List[dict[str, str]] = []

        for item in request.resources:
            if item.type == "audio":
                multi_contents.append({"audio": item.path})

            elif item.type == "image":
                multi_contents.append({"image": item.path})

        user_content = [image_content for image_content in multi_contents]

        if not request.prompt:
            request.prompt = "请描述图像内容"
        user_content.append({"text": request.prompt})

        return {"role": "user", "content": user_content}

    def _build_messages(self, request: ModelRequest) -> List[dict]:
        messages = []

        if request.system:
            messages.append({"role": "system", "content": request.system})

        for msg in request.history:
            user_msg = (
                self.__build_multi_messages(ModelRequest(msg.message, resources=msg.resources))
                if all((self.config.multimodal, msg.resources))
                else {"role": "user", "content": msg.message}
            )
            messages.append(user_msg)
            messages.append({"role": "assistant", "content": msg.respond})

        user_msg = (
            {"role": "user", "content": request.prompt}
            if not request.resources
            else self.__build_multi_messages(ModelRequest(request.prompt, resources=request.resources))
        )

        messages.append(user_msg)

        return messages

    async def _GenerationResponse_handle(
        self,
        messages: list,
        tools: List[dict],
        response_format: Optional[dict],
        response: GenerationResponse | MultiModalConversationResponse,
        total_tokens: int,
    ) -> ModelCompletions:
        """
        处理 Dashscope 的非流式返回对象

        :param message: 总消息列表，用于工具调用
        :param tools: 工具列表
        :param response_format: 消息回复格式
        :param response: 迭代器主体
        :param total_tokens: 整个对话的总 token
        """
        completions = ModelCompletions()

        if response.status_code != 200:
            completions.succeed = False
            logger.error(f"模型调用失败: {response.status_code}({response.code})")
            logger.error(f"{response.message}")
            completions.text = f"模型调用失败: {response.status_code}({response.code})"
            return completions

        total_tokens += int(response.usage.total_tokens)
        completions.usage = total_tokens

        if response.output.text:
            completions.text = response.output.text
            return completions

        message_content = response.output.choices[0].message.content
        if message_content:
            completions.text = message_content if isinstance(message_content, str) else message_content[0].get("text")
            return completions

        return await self._tool_calls_handle_sync(messages, tools, response_format, response, total_tokens)

    async def _Generator_handle(
        self,
        messages: list,
        tools: List[dict],
        response_format: Optional[dict],
        response: Generator[GenerationResponse, None, None] | Generator[MultiModalConversationResponse, None, None],
        total_tokens: int = 0,
    ) -> AsyncGenerator[ModelStreamCompletions, None]:
        """
        处理 Dashscope 的流式迭代器

        :param message: 总消息列表，用于工具调用
        :param tools: 工具列表
        :param response_format: 消息回复格式
        :param response: 迭代器主体
        :param total_tokens: 整个对话的总 token
        """
        func_stream = FunctionCallStream()
        thought_stream = ThoughtStream()

        for chunk in response:
            logger.debug(chunk)
            stream_completions = ModelStreamCompletions()

            if chunk.status_code != 200:
                logger.error(f"模型调用失败: {chunk.status_code}({chunk.code})")
                logger.error(f"{chunk.message}")
                stream_completions.chunk = f"模型调用失败: {chunk.status_code}({chunk.code})"
                stream_completions.succeed = False

                yield stream_completions
                return

            # 更新 token 消耗
            total_tokens = chunk.usage.total_tokens
            stream_completions.usage = total_tokens

            # 优先判断是否是工具调用（OpenAI-style function calling）
            if chunk.output.choices and chunk.output.choices[0].message.get("tool_calls", []):
                func_stream.from_chunk(chunk)
                # 工具调用也可能在输出文本之后发生

            # DashScope 的 text 模式（非标准接口）
            if hasattr(chunk.output, "text") and chunk.output.text:
                stream_completions.chunk = chunk.output.text
                yield stream_completions
                continue

            if chunk.output.choices is None:
                continue

            stream_completions.chunk = thought_stream.process_chunk(chunk)
            yield stream_completions

        # 流式处理工具调用响应
        if func_stream.enable:
            async for final_chunk in await self._tool_calls_handle_stream(
                messages, tools, response_format, func_stream, total_tokens
            ):
                yield final_chunk

    async def _tool_calls_handle_sync(
        self,
        messages: List,
        tools: List[dict],
        response_format: Optional[dict],
        response: GenerationResponse | MultiModalConversationResponse,
        total_tokens: int,
    ) -> ModelCompletions:
        """
        处理非流式工具调用流

        :param messages: 消息列表
        :param tools: 工具列表
        :param response_format: 消息回复格式
        :param func_stream: 工具调用流实例
        :param total_tokens: 总 Token 数
        """
        tool_call = response.output.choices[0].message.tool_calls[0]
        tool_call_id = tool_call["id"]
        function_name = tool_call["function"]["name"]
        function_args = json.loads(tool_call["function"]["arguments"])

        function_return = await function_call_handler(function_name, function_args)

        messages.append(response.output.choices[0].message)
        messages.append({"role": "tool", "content": function_return, "tool_call_id": tool_call_id})

        return await self._ask(messages, tools, response_format, total_tokens)  # type: ignore

    async def _tool_calls_handle_stream(
        self,
        messages: List,
        tools: List[dict],
        response_format: Optional[dict],
        func_stream: FunctionCallStream,
        total_tokens: int,
    ) -> AsyncGenerator[ModelStreamCompletions, None]:
        """
        处理流式工具调用流

        :param messages: 消息列表
        :param tools: 工具列表
        :param response_format: 消息回复格式
        :param func_stream: 工具调用流实例
        :param total_tokens: 总 Token 数
        """
        function_args = json.loads(func_stream.function_args)

        function_return = await function_call_handler(func_stream.function_name, function_args)  # type: ignore

        messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": func_stream.id,
                        "function": {
                            "arguments": func_stream.function_args,
                            "name": func_stream.function_name,
                        },
                        "type": "function",
                        "index": 0,
                    }
                ],
            }
        )
        messages.append({"role": "tool", "content": function_return, "tool_call_id": func_stream.id})

        return await self._ask(messages, tools, response_format, total_tokens)  # type: ignore

    async def _ask(
        self,
        messages: list,
        tools: List[dict],
        response_format: Optional[dict],
        total_tokens: int = 0,
    ) -> Union[ModelCompletions, AsyncGenerator[ModelStreamCompletions, None]]:
        loop = asyncio.get_event_loop()

        # 因为 Dashscope 对于多模态模型的接口不同，所以这里不能统一函数
        if not self.config.multimodal:
            response = await loop.run_in_executor(
                None,
                partial(
                    dashscope.Generation.call,
                    api_key=self.api_key,
                    model=self.model,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    repetition_penalty=self.repetition_penalty,
                    stream=self.stream,
                    tools=tools,
                    parallel_tool_calls=True,
                    enable_search=self.enable_search,
                    incremental_output=self.stream,  # 给他调成一样的：这个参数只支持流式调用时设置为True
                    headers=self.extra_headers,
                    enable_thinking=self.enable_thinking,
                    thinking_budget=self.thinking_budget,
                    response_format=response_format,
                ),
            )
        else:
            response = await loop.run_in_executor(
                None,
                partial(
                    dashscope.MultiModalConversation.call,
                    api_key=self.api_key,
                    model=self.model,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    repetition_penalty=self.repetition_penalty,
                    stream=self.stream,
                    tools=tools,
                    parallel_tool_calls=True,
                    enable_search=self.enable_search,
                    incremental_output=self.stream,
                    response_format=response_format,
                ),
            )

        if isinstance(response, GenerationResponse) or isinstance(response, MultiModalConversationResponse):
            return await self._GenerationResponse_handle(messages, tools, response_format, response, total_tokens)
        return self._Generator_handle(messages, tools, response_format, response, total_tokens)

    @overload
    async def ask(self, request: ModelRequest, *, stream: Literal[False] = False) -> ModelCompletions: ...

    @overload
    async def ask(
        self, request: ModelRequest, *, stream: Literal[True] = True
    ) -> AsyncGenerator[ModelStreamCompletions, None]: ...

    async def ask(
        self, request: ModelRequest, *, stream: bool = False
    ) -> Union[ModelCompletions, AsyncGenerator[ModelStreamCompletions, None]]:
        self.stream = stream if stream is not None else False

        tools = request.tools if request.tools else []
        messages = self._build_messages(request)
        if request.format == "json" and request.json_schema:
            logger.warning("该模型加载器不支持传入 Json Schema 模型，请确保您已经在模型提示词中传入了相关 json 字段")
            response_format = {"type": "json_object"}
        else:
            response_format = None

        return await self._ask(messages, tools, response_format)
