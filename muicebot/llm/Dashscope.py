import asyncio
import json
import pathlib
from functools import partial
from typing import (
    AsyncGenerator,
    Generator,
    List,
    Literal,
    Optional,
    Union,
    overload,
)

import dashscope
from dashscope.api_entities.dashscope_response import (
    GenerationResponse,
    MultiModalConversationResponse,
)
from nonebot import logger

from ._types import BasicModel, Message, ModelConfig, function_call_handler
from .utils.auto_system_prompt import auto_system_prompt


class Dashscope(BasicModel):
    def __init__(self, model_config: ModelConfig) -> None:
        super().__init__(model_config)
        self._require("api_key", "model_name")
        self.api_key = self.config.api_key
        self.model = self.config.model_name
        self.max_tokens = self.config.max_tokens
        self.temperature = self.config.temperature
        self.top_p = self.config.top_p
        self.repetition_penalty = self.config.repetition_penalty
        self.system_prompt = self.config.system_prompt
        self.auto_system_prompt = self.config.auto_system_prompt
        self.enable_search = self.config.online_search

        self._tools: List[dict] = []

    def __build_image_message(self, prompt: str, image_paths: List[str]) -> dict:
        image_contents = []
        for image_path in image_paths:
            if not (image_path.startswith("http") or image_path.startswith("file")):
                abs_path = pathlib.Path(image_path).resolve()
                image_path = abs_path.as_uri()
                image_path = image_path.replace("file:///", "file://")

            image_contents.append({"image": image_path})

        user_content = [image_content for image_content in image_contents]

        if not prompt:
            prompt = "请描述图像内容"
        user_content.append({"type": "text", "text": prompt})

        return {"role": "user", "content": user_content}

    def _build_messages(self, prompt: str, history: List[Message], image_paths: Optional[List[str]] = None) -> list:
        messages = []

        if self.auto_system_prompt:
            self.system_prompt = auto_system_prompt(prompt)
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        for msg in history:
            user_msg = (
                {"role": "user", "content": msg.message}
                if not msg.images
                else self.__build_image_message(msg.message, msg.images)
            )
            messages.append(user_msg)
            messages.append({"role": "assistant", "content": msg.respond})

        user_msg = (
            {"role": "user", "content": prompt} if not image_paths else self.__build_image_message(prompt, image_paths)
        )

        messages.append(user_msg)

        return messages

    async def _ask_sync(self, messages: list) -> str:
        loop = asyncio.get_event_loop()

        response = await loop.run_in_executor(
            None,
            partial(
                dashscope.Generation.call,
                api_key=self.api_key,
                model=self.model,
                messages=messages,
                tools=self._tools,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                top_p=self.top_p,
                repetition_penalty=self.repetition_penalty,
                stream=False,
                enable_search=self.enable_search,
            ),
        )

        if not isinstance(response, GenerationResponse):
            return "(模型内部错误：在流关闭的情况下返回了 Generator)"

        if response.status_code != 200:
            logger.error(f"模型调用失败: {response.status_code}({response.code})")
            logger.error(f"{response.message}")
            return f"模型调用失败: {response.status_code}({response.code})"

        if response.output.text:
            return response.output.text

        message_content = response.output.choices[0].message.content
        if message_content:
            return message_content if isinstance(message_content, str) else "".join(message_content)

        tool_call = response.output.choices[0].message.tool_calls[0]
        tool_call_id = tool_call["id"]
        function_name = tool_call["function"]["name"]
        function_args = json.loads(tool_call["function"]["arguments"])

        logger.info(f"function call 请求 {function_name}, 参数: {function_args}")
        function_return = await function_call_handler(function_name, function_args)
        logger.success(f"Function call 成功，返回: {function_return}")

        messages.append(response.output.choices[0].message)
        messages.append({"role": "tool", "content": function_return, "tool_call_id": tool_call_id})

        return await self._ask_sync(messages)

    async def _ask_stream(self, messages: list) -> AsyncGenerator[str, None]:
        loop = asyncio.get_event_loop()

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
                stream=True,
                tools=self._tools,
                parallel_tool_calls=True,
                enable_search=self.enable_search,
                incremental_output=True,
            ),
        )

        if isinstance(response, GenerationResponse):
            logger.warning("模型内部错误：在流开启的情况下返回了 GenerationResponse")
            yield response.output.text
            return

        is_insert_think_label = False
        is_function_call = False
        size = 0

        tool_call_id: str = ""
        function_name: str = ""
        function_args_delta: str = ""

        for chunk in response:
            logger.debug(chunk)

            if chunk.status_code != 200:
                logger.error(f"模型调用失败: {chunk.status_code}({chunk.code})")
                logger.error(f"{chunk.message}")
                yield f"模型调用失败: {chunk.status_code}({chunk.code})"
                return

            if chunk.output.choices and chunk.output.choices[0].message.get("tool_calls", []):
                tool_calls = chunk.output.choices[0].message.tool_calls
                tool_call = tool_calls[0]
                if tool_call.get("id", ""):
                    tool_call_id = tool_call["id"]
                if tool_call.get("function", {}).get("name", ""):
                    function_name = tool_call.get("function").get("name")
                function_arg = tool_call.get("function", {}).get("arguments", "")
                if function_arg and function_args_delta != function_arg:
                    function_args_delta += function_arg
                is_function_call = True
                continue

            if hasattr(chunk.output, "text") and chunk.output.text:  # 傻逼 Dashscope 为什么不统一接口？
                yield chunk.output.text[size:]
                size = len(chunk.output.text)
                continue

            answer_content = chunk.output.choices[0].message.content
            reasoning_content = chunk.output.choices[0].message.get("reasoning_content", "")
            if answer_content == "" and reasoning_content == "":
                continue

            if reasoning_content != "" and answer_content == "":
                yield (reasoning_content if is_insert_think_label else "<think>" + reasoning_content)
                is_insert_think_label = True

            elif answer_content != "":
                if isinstance(answer_content, list):
                    answer_content = "".join(answer_content)  # 不知道为什么会是list
                yield (answer_content if not is_insert_think_label else "</think>" + answer_content)
                is_insert_think_label = False

        if not is_function_call:
            return

        function_args = json.loads(function_args_delta)

        logger.info(f"function call 请求 {function_name}, 参数: {function_args}")
        function_return = await function_call_handler(function_name, function_args)  # type:ignore
        logger.success(f"Function call 成功，返回: {function_return}")

        messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": tool_call_id,
                        "function": {
                            "arguments": function_args_delta,
                            "name": function_name,
                        },
                        "type": "function",
                        "index": 0,
                    }
                ],
            }
        )
        messages.append({"role": "tool", "content": function_return, "tool_call_id": tool_call_id})

        async for chunk in self._ask_stream(messages):
            yield chunk

        return

    async def _ask_vision_sync(self, messages: list) -> str:
        loop = asyncio.get_event_loop()

        response = await loop.run_in_executor(
            None,
            partial(
                dashscope.MultiModalConversation.call,
                api_key=self.api_key,
                model=self.model,
                messages=messages,
                stream=False,
            ),
        )

        if isinstance(response, Generator):
            return "(模型内部错误: 在流关闭的情况下返回了 Generator)"

        if response.status_code != 200:
            logger.error(f"模型调用失败: {response.status_code}({response.code})")
            logger.error(f"{response.message}")
            return f"模型调用失败: {response.status_code}({response.code})"

        if isinstance(response.output.choices[0].message.content, str):
            return response.output.choices[0].message.content

        return response.output.choices[0].message.content[0]["text"]  # type: ignore

    async def _ask_vision_stream(self, messages: list) -> AsyncGenerator[str, None]:
        loop = asyncio.get_event_loop()

        response = await loop.run_in_executor(
            None,
            partial(
                dashscope.MultiModalConversation.call,
                api_key=self.api_key,
                model=self.model,
                messages=messages,
                stream=True,
            ),
        )

        if isinstance(response, MultiModalConversationResponse):
            logger.warning("模型内部错误：在流开启的情况下返回了 MultiModalConversationResponse")
            if isinstance(response.output.choices[0].message.content, str):
                yield response.output.choices[0].message.content
            else:
                yield response.output.choices[0].message.content[0]["text"]
            return

        size = 0

        for chunk in response:
            logger.debug(chunk)
            if chunk.status_code != 200:
                logger.error(f"模型调用失败: {chunk.status_code}({chunk.code})")
                logger.error(f"{chunk.message}")
                yield f"模型调用失败: {chunk.status_code}({chunk.code})"
                return

            content_body = chunk.output.choices[0].message.content
            if isinstance(content_body, str):
                yield content_body[size:]
                size = len(content_body)
            else:
                yield content_body[0]["text"][size:]
                size = len(content_body[0]["text"])

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
        因为 Dashscope 对于多模态模型的接口不同，所以这里不能统一函数
        """
        self._tools = tools if tools else []
        messages = self._build_messages(prompt, history, images)

        if stream:
            if self.config.multimodal:
                return self._ask_vision_stream(messages)
            return self._ask_stream(messages)

        if self.config.multimodal:
            return await self._ask_vision_sync(messages)
        return await self._ask_sync(messages)
