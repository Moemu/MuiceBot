from typing import (
    AsyncGenerator,
    Awaitable,
    List,
    Literal,
    Optional,
    Type,
    Union,
    overload,
)

from google import genai
from google.genai import errors
from google.genai.types import (
    Content,
    ContentOrDict,
    GenerateContentConfig,
    GoogleSearch,
    HarmBlockThreshold,
    HarmCategory,
    Part,
    SafetySetting,
    Tool,
)
from httpx import ConnectError
from nonebot import logger
from pydantic import BaseModel

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


@register("gemini")
class Gemini(BaseLLM):
    def __init__(self, model_config: ModelConfig) -> None:
        super().__init__(model_config)
        self._require("model_name", "api_key")

        self.model_name = self.config.model_name
        self.api_key = self.config.api_key
        self.enable_search = self.config.online_search

        self.client = genai.Client(api_key=self.api_key)

        self.gemini_config = GenerateContentConfig(
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            top_k=self.config.top_k,
            max_output_tokens=self.config.max_tokens,
            presence_penalty=self.config.presence_penalty,
            frequency_penalty=self.config.frequency_penalty,
            response_modalities=[m.upper() for m in self.config.modalities if m in {"image", "text"}],
            safety_settings=(
                [
                    SafetySetting(
                        category=HarmCategory.HARM_CATEGORY_HARASSMENT,
                        threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    ),
                    SafetySetting(
                        category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                        threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    ),
                    SafetySetting(
                        category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                        threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    ),
                    SafetySetting(
                        category=HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY,
                        threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    ),
                ]
                if self.config.content_security
                else []
            ),
        )

    def _build_gemini_config(
        self, tools: Optional[List[dict]], response_format: Optional[Type[BaseModel]]
    ) -> GenerateContentConfig:
        gemini_config = self.gemini_config.model_copy()
        format_tools = []

        # build tools
        for tool in tools if tools else []:
            tool = tool["function"]
            required_parameters = tool["required"]
            del tool["required"]
            tool["parameters"]["required"] = required_parameters
            format_tools.append(tool)

        function_tools = Tool(function_declarations=format_tools)  # type: ignore

        if self.enable_search:
            function_tools.google_search = GoogleSearch()

        if tools or self.enable_search:
            gemini_config.tools = [function_tools]

        # build response format
        if response_format:
            gemini_config.response_mime_type = "application/json"
            gemini_config.response_schema = response_format

        return gemini_config

    def _build_user_parts(self, request: ModelRequest) -> list[Part]:
        user_parts: list[Part] = [Part.from_text(text=request.prompt)]

        if not request.resources:
            return user_parts

        for resource in request.resources:
            if resource.type == "image" and resource.path is not None:
                user_parts.append(
                    Part.from_bytes(
                        data=get_file_base64(resource.path), mime_type=resource.mimetype or "image/jpeg"  # type: ignore
                    )
                )

        return user_parts

    def _build_messages(self, request: ModelRequest) -> list[ContentOrDict]:
        messages: List[ContentOrDict] = []

        if request.history:
            for index, item in enumerate(request.history):
                messages.append(
                    Content(
                        role="user", parts=self._build_user_parts(ModelRequest(item.message, resources=item.resources))
                    )
                )
                messages.append(Content(role="model", parts=[Part.from_text(text=item.respond)]))

        messages.append(Content(role="user", parts=self._build_user_parts(request)))

        return messages

    async def _ask_sync(
        self,
        messages: list[ContentOrDict],
        tools: Optional[List[dict]],
        response_format: Optional[Type[BaseModel]],
        total_tokens: int = 0,
    ) -> ModelCompletions:
        gemini_config = self._build_gemini_config(tools, response_format)
        completions = ModelCompletions()

        try:
            chat = self.client.aio.chats.create(model=self.model_name, config=gemini_config, history=messages[:-1])
            message = messages[-1].parts  # type: ignore
            response = await chat.send_message(message=message)  # type: ignore
            if response.usage_metadata:
                total_token_count = response.usage_metadata.total_token_count
                total_tokens += total_token_count if total_token_count else 0

            if response.text:
                completions.text = response.text

            if (
                response.candidates
                and response.candidates[0].content
                and response.candidates[0].content.parts
                and response.candidates[0].content.parts[0].inline_data
                and response.candidates[0].content.parts[0].inline_data.data
            ):
                completions.resources = [
                    Resource(type="image", raw=response.candidates[0].content.parts[0].inline_data.data)
                ]

            if response.function_calls:
                function_call = response.function_calls[0]
                function_name = function_call.name
                function_args = function_call.args

                function_return = await function_call_handler(function_name, function_args)  # type: ignore

                function_response_part = Part.from_function_response(
                    name=function_name,  # type: ignore
                    response={"result": function_return},
                )

                messages.append(Content(role="model", parts=[Part(function_call=function_call)]))
                messages.append(Content(role="user", parts=[function_response_part]))

                return await self._ask_sync(messages, tools, response_format, total_tokens)

            completions.text = completions.text or "（警告：模型无输出！）"
            completions.usage = total_tokens
            return completions

        except errors.APIError as e:
            error_message = f"API 状态异常: {e.code}({e.response})"
            completions.text = error_message
            completions.succeed = False
            logger.error(error_message)
            logger.error(e.message)
            return completions

        except ConnectError:
            error_message = "模型加载器连接超时"
            completions.text = error_message
            completions.succeed = False
            logger.error(error_message)
            return completions

    async def _ask_stream(
        self,
        messages: list,
        tools: Optional[List[dict]],
        response_format: Optional[Type[BaseModel]],
        total_tokens: int = 0,
    ) -> AsyncGenerator[ModelStreamCompletions, None]:
        gemini_config = self._build_gemini_config(tools, response_format)
        try:
            current_total_tokens = 0
            stream = await self.client.aio.models.generate_content_stream(
                model=self.model_name, contents=messages, config=gemini_config
            )
            stream = await stream if isinstance(stream, Awaitable) else stream
            async for chunk in stream:
                stream_completions = ModelStreamCompletions()

                if chunk.text:
                    stream_completions.chunk = chunk.text
                    yield stream_completions

                if chunk.usage_metadata and chunk.usage_metadata.total_token_count:
                    current_total_tokens = chunk.usage_metadata.total_token_count

                if (
                    chunk.candidates
                    and chunk.candidates[0].content
                    and chunk.candidates[0].content.parts
                    and chunk.candidates[0].content.parts[0].inline_data
                    and chunk.candidates[0].content.parts[0].inline_data.data
                ):
                    stream_completions.resources = [
                        Resource(type="image", raw=chunk.candidates[0].content.parts[0].inline_data.data)
                    ]
                    yield stream_completions

                if chunk.function_calls:
                    function_call = chunk.function_calls[0]
                    function_name = function_call.name
                    function_args = function_call.args

                    function_return = await function_call_handler(function_name, function_args)  # type: ignore

                    function_response_part = Part.from_function_response(
                        name=function_name,  # type: ignore
                        response={"result": function_return},
                    )

                    messages.append(Content(role="model", parts=[Part(function_call=function_call)]))
                    messages.append(Content(role="user", parts=[function_response_part]))

                    async for final_chunk in self._ask_stream(
                        messages, tools, response_format, total_tokens + current_total_tokens
                    ):
                        yield final_chunk
                    return

            totaltokens_completions = ModelStreamCompletions()

            total_tokens += current_total_tokens
            totaltokens_completions.usage = total_tokens
            yield totaltokens_completions

        except errors.APIError as e:
            stream_completions = ModelStreamCompletions()
            error_message = f"API 状态异常: {e.code}({e.response})"
            stream_completions.chunk = error_message
            logger.error(error_message)
            logger.error(e.message)
            stream_completions.succeed = False
            yield stream_completions
            return

        except ConnectError:
            stream_completions = ModelStreamCompletions()
            error_message = "模型加载器连接超时"
            stream_completions.chunk = error_message
            logger.error(error_message)
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
        messages = self._build_messages(request)
        response_format = request.json_schema if request.format == "json" else None

        if stream:
            return self._ask_stream(messages, request.tools, response_format)

        return await self._ask_sync(messages, request.tools, response_format)
