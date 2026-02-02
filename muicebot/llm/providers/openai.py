import base64
import json
from io import BytesIO
from typing import AsyncGenerator, List, Literal, Union, overload

import openai
from nonebot import logger
from openai import NOT_GIVEN, NotGiven
from openai.types.chat import ChatCompletionMessage, ChatCompletionToolParam
from openai.types.shared_params.response_format_json_schema import (
    JSONSchema,
    ResponseFormatJSONSchema,
)

from muicebot.models import Resource

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


@register("openai")
class Openai(BaseLLM):
    _tools: List[ChatCompletionToolParam]
    modalities: Union[List[Literal["text", "audio"]], NotGiven]

    def __init__(self, model_config: ModelConfig) -> None:
        super().__init__(model_config)
        self._require("api_key", "model_name")
        self.api_key = self.config.api_key
        self.model = self.config.model_name
        self.api_base = self.config.api_host or "https://api.openai.com/v1"
        self.max_tokens = self.config.max_tokens
        self.temperature = self.config.temperature
        self.stream = self.config.stream
        self.modalities = [m for m in self.config.modalities if m in {"text", "audio"}] or NOT_GIVEN  # type: ignore
        self.audio = self.config.audio if (self.modalities and self.config.audio) else NOT_GIVEN
        self.extra_body = self.config.extra_body

        self.client = openai.AsyncOpenAI(api_key=self.api_key, base_url=self.api_base, timeout=30)

    def __build_multi_messages(self, request: ModelRequest) -> dict:
        """
        构建多模态类型

        此模型加载器支持的多模态类型: `audio` `image` `video` `file`
        """
        user_content: List[dict] = [{"type": "text", "text": request.prompt}]

        for resource in request.resources:
            if resource.path is None:
                continue

            elif resource.type == "audio":
                file_format = resource.path.split(".")[-1]
                file_data = f"data:;base64,{get_file_base64(local_path=resource.path)}"
                user_content.append({"type": "input_audio", "input_audio": {"data": file_data, "format": file_format}})

            elif resource.type == "image":
                file_format = resource.path.split(".")[-1]
                file_data = f"data:image/{file_format};base64,{get_file_base64(local_path=resource.path)}"
                user_content.append({"type": "image_url", "image_url": {"url": file_data}})

            elif resource.type == "video":
                file_format = resource.path.split(".")[-1]
                file_data = f"data:;base64,{get_file_base64(local_path=resource.path)}"
                user_content.append({"type": "video_url", "video_url": {"url": file_data}})

            elif resource.type == "file":
                file_format = resource.path.split(".")[-1]
                file_data = f"data:;base64,{get_file_base64(local_path=resource.path)}"
                user_content.append({"type": "file", "file": {"file_data": file_data}})

        return {"role": "user", "content": user_content}

    def _build_messages(self, request: ModelRequest) -> list:
        messages = []

        if request.system:
            messages.append({"role": "system", "content": request.system})

        if request.history:
            for index, item in enumerate(request.history):
                user_content = (
                    {"role": "user", "content": item.message}
                    if not all([item.resources, self.config.multimodal])
                    else self.__build_multi_messages(ModelRequest(item.message, resources=item.resources))
                )

                messages.append(user_content)
                messages.append({"role": "assistant", "content": item.respond})

        user_content = (
            {"role": "user", "content": request.prompt}
            if not request.resources
            else self.__build_multi_messages(request)
        )

        messages.append(user_content)

        return messages

    def _tool_call_request_precheck(self, message: ChatCompletionMessage) -> bool:
        """
        工具调用请求预检
        """
        # We expect a single tool call
        if not (message.tool_calls and len(message.tool_calls) == 1):
            return False

        # We expect the tool to be a function call
        tool_call = message.tool_calls[0]
        if tool_call.type != "function":
            return False

        return True

    async def _ask_sync(
        self,
        messages: list,
        tools: Union[List[ChatCompletionToolParam], NotGiven],
        response_format: Union[ResponseFormatJSONSchema, NotGiven],
        total_tokens: int = 0,
    ) -> ModelCompletions:
        completions = ModelCompletions()

        try:
            response = await self.client.chat.completions.create(
                audio=self.audio,
                model=self.model,
                modalities=self.modalities,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stream=False,
                tools=tools,
                extra_body=self.extra_body,
                response_format=response_format,
            )

            logger.debug(f"OpenAI response: id={response.id}, choices={response.choices}, usage={response.usage}")

            result = ""
            message = response.choices[0].message  # type: ignore
            total_tokens += response.usage.total_tokens if response.usage else 0

            if (
                hasattr(message, "reasoning_content")  # type: ignore
                and message.reasoning_content  # type: ignore
            ):
                result += f"<think>{message.reasoning_content}</think>"  # type: ignore

            if response.choices[0].finish_reason == "tool_calls" and self._tool_call_request_precheck(
                response.choices[0].message
            ):
                messages.append(response.choices[0].message)
                tool_call = response.choices[0].message.tool_calls[0]  # type: ignore
                arguments = json.loads(tool_call.function.arguments.replace("'", '"'))

                function_return = await function_call_handler(tool_call.function.name, arguments)

                messages.append(
                    {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": tool_call.function.name,
                        "content": function_return,
                    }
                )
                return await self._ask_sync(messages, tools, response_format, total_tokens)

            if message.content:  # type: ignore
                result += message.content  # type: ignore

            # 多模态消息处理（目前仅支持 audio 输出）
            if response.choices[0].message.audio:
                wav_bytes = base64.b64decode(response.choices[0].message.audio.data)
                completions.resources = [Resource(type="audio", raw=wav_bytes)]

            completions.text = result or "（警告：模型无输出！）"
            completions.usage = total_tokens

        except openai.APIConnectionError as e:
            error_message = f"API 连接错误: {e}"
            completions.text = error_message
            logger.error(error_message)
            logger.error(e.__cause__)
            completions.succeed = False

        except openai.APIStatusError as e:
            error_message = f"API 状态异常: {e.status_code}({e.response})"
            completions.text = error_message
            logger.error(error_message)
            completions.succeed = False

        return completions

    async def _ask_stream(
        self,
        messages: list,
        tools: Union[List[ChatCompletionToolParam], NotGiven],
        response_format: Union[ResponseFormatJSONSchema, NotGiven],
        total_tokens: int = 0,
    ) -> AsyncGenerator[ModelStreamCompletions, None]:
        is_insert_think_label = False
        function_id = ""
        function_name = ""
        function_arguments = ""
        audio_string = ""

        try:
            response = await self.client.chat.completions.create(
                audio=self.audio,
                model=self.model,
                modalities=self.modalities,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stream=True,
                stream_options={"include_usage": True},
                tools=tools,
                extra_body=self.extra_body,
                response_format=response_format,
            )

            async for chunk in response:
                stream_completions = ModelStreamCompletions()

                logger.debug(f"OpenAI response: id={chunk.id}, choices={chunk.choices}, usage={chunk.usage}")

                # 获取 usage （最后一个包中返回）
                if chunk.usage:
                    total_tokens += chunk.usage.total_tokens
                    stream_completions.usage = total_tokens

                if not chunk.choices:
                    yield stream_completions
                    continue

                # 处理 Function call
                if chunk.choices[0].delta.tool_calls:
                    tool_call = chunk.choices[0].delta.tool_calls[0]
                    if tool_call.id:
                        function_id = tool_call.id
                    if tool_call.function:
                        if tool_call.function.name:
                            function_name += tool_call.function.name
                        if tool_call.function.arguments:
                            function_arguments += tool_call.function.arguments

                delta = chunk.choices[0].delta
                answer_content = delta.content

                # 处理思维过程 reasoning_content
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:  # type: ignore
                    reasoning_content = chunk.choices[0].delta.reasoning_content  # type: ignore
                    stream_completions.chunk = (
                        reasoning_content if is_insert_think_label else "<think>" + reasoning_content
                    )
                    yield stream_completions
                    is_insert_think_label = True

                elif answer_content:
                    stream_completions.chunk = (
                        answer_content if not is_insert_think_label else "</think>" + answer_content
                    )
                    yield stream_completions
                    is_insert_think_label = False

                # 处理多模态消息 (audio-only) (非标准方法，可能出现问题)
                if hasattr(chunk.choices[0].delta, "audio"):
                    audio = chunk.choices[0].delta.audio  # type: ignore
                    if audio.get("data", None):
                        audio_string += audio.get("data")
                    stream_completions.chunk = audio.get("transcript", "")
                    yield stream_completions

            if function_id:

                function_return = await function_call_handler(function_name, json.loads(function_arguments))

                messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": function_id,
                                "type": "function",
                                "function": {"name": function_name, "arguments": function_arguments},
                            }
                        ],
                    }
                )
                messages.append(
                    {
                        "tool_call_id": function_id,
                        "role": "tool",
                        "content": function_return,
                    }
                )

                async for chunk in self._ask_stream(messages, tools, response_format, total_tokens):
                    yield chunk
                return

            # 处理多模态返回
            if audio_string:
                import numpy as np
                import soundfile as sf

                wav_bytes = base64.b64decode(audio_string)
                pcm_data = np.frombuffer(wav_bytes, dtype=np.int16)
                wav_io = BytesIO()
                sf.write(wav_io, pcm_data, samplerate=24000, format="WAV")

                stream_completions = ModelStreamCompletions()
                stream_completions.resources = [Resource(type="audio", raw=wav_io)]
                yield stream_completions

        except openai.APIConnectionError as e:
            error_message = f"API 连接错误: {e}"
            logger.error(error_message)
            logger.error(e.__cause__)
            stream_completions = ModelStreamCompletions()
            stream_completions.chunk = error_message
            stream_completions.succeed = False
            yield stream_completions

        except openai.APIStatusError as e:
            error_message = f"API 状态异常: {e.status_code}({e.response})"
            logger.error(error_message)
            stream_completions = ModelStreamCompletions()
            stream_completions.chunk = error_message
            stream_completions.succeed = False
            yield stream_completions

    @overload
    async def ask(self, request: ModelRequest, *, stream: Literal[False] = False) -> ModelCompletions: ...

    @overload
    async def ask(
        self, request: ModelRequest, *, stream: Literal[True] = True
    ) -> AsyncGenerator[ModelStreamCompletions, None]: ...

    async def ask(
        self, request: ModelRequest, *, stream: bool = False
    ) -> Union[ModelCompletions, AsyncGenerator[ModelStreamCompletions, None]]:
        tools = request.tools if request.tools else NOT_GIVEN

        messages = self._build_messages(request)
        if request.format == "json" and request.json_schema:
            response_format = ResponseFormatJSONSchema(
                type="json_schema", json_schema=JSONSchema(**request.json_schema.model_json_schema(), strict=True)
            )
        else:
            response_format = NOT_GIVEN

        if stream:
            return self._ask_stream(messages, tools, response_format)  # type: ignore

        return await self._ask_sync(messages, tools, response_format)  # type: ignore
