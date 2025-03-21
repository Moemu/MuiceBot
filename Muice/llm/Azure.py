import os
from typing import AsyncGenerator, List, Literal, Optional, Union, overload

from azure.ai.inference.aio import ChatCompletionsClient
from azure.ai.inference.models import (
    AssistantMessage,
    ChatRequestMessage,
    ContentItem,
    ImageContentItem,
    ImageDetailLevel,
    ImageUrl,
    SystemMessage,
    TextContentItem,
    UserMessage,
)
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError
from nonebot import logger

from ._types import BasicModel, Message, ModelConfig
from .utils.auto_system_prompt import auto_system_prompt


class Azure(BasicModel):
    def __init__(self, model_config: ModelConfig) -> None:
        super().__init__(model_config)
        self._require("model_name")
        self.model_name = self.config.model_name
        self.system_prompt = self.config.system_prompt
        self.auto_system_prompt = self.config.auto_system_prompt
        self.user_instructions = self.config.user_instructions
        self.auto_user_instructions = self.config.auto_user_instructions
        self.max_tokens = self.config.max_tokens
        self.temperature = self.config.temperature
        self.top_p = self.config.top_p
        self.frequency_penalty = self.config.frequency_penalty
        self.presence_penalty = self.config.presence_penalty
        self.token = os.getenv("AZURE_API_KEY", self.config.api_key)
        self.endpoint = self.config.api_host if self.config.api_host else "https://models.inference.ai.azure.com"

    def __build_image_messages(self, prompt: str, image_paths: list) -> UserMessage:
        image_content_items: List[ContentItem] = []

        for item in image_paths:
            image_content_items.append(
                ImageContentItem(
                    image_url=ImageUrl.load(
                        image_file=item, image_format=item.split(".")[-1], detail=ImageDetailLevel.AUTO
                    )
                )
            )

        content = [TextContentItem(text=prompt)] + image_content_items

        return UserMessage(content=content)

    def _build_messages(
        self, prompt: str, history: List[Message], image_paths: Optional[List] = None
    ) -> List[ChatRequestMessage]:
        messages: List[ChatRequestMessage] = []

        if self.auto_system_prompt:
            self.system_prompt = auto_system_prompt(prompt)

        if self.system_prompt:
            messages.append(SystemMessage(self.system_prompt))

        for msg in history:
            user_msg = (
                UserMessage(msg.message)
                if not msg.images
                else self.__build_image_messages(msg.message, image_paths=msg.images)
            )
            messages.append(user_msg)
            messages.append(AssistantMessage(msg.respond))

        if self.auto_user_instructions:
            self.user_instructions = auto_system_prompt(prompt)

        if self.user_instructions and not history:
            user_message = self.user_instructions + "\n" + prompt
        else:
            user_message = prompt

        user_message = (
            UserMessage(user_message) if not image_paths else self.__build_image_messages(prompt, image_paths)
        )

        messages.append(user_message)

        return messages

    async def _ask_sync(self, messages: List[ChatRequestMessage]) -> str:
        client = ChatCompletionsClient(endpoint=self.endpoint, credential=AzureKeyCredential(self.token))

        try:
            response = await client.complete(
                messages=messages,
                model=self.model_name,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                top_p=self.top_p,
                frequency_penalty=self.frequency_penalty,
                presence_penalty=self.presence_penalty,
                stream=False,
            )
            return response.choices[0].message.content  # type: ignore
        except HttpResponseError as e:
            logger.error(f"模型响应失败: {e.status_code} ({e.reason})")
            logger.error(f"{e.message}")
            return f"模型响应失败: {e.status_code} ({e.reason})"
        finally:
            await client.close()

    async def _ask_stream(self, messages: List[ChatRequestMessage]) -> AsyncGenerator[str, None]:
        client = ChatCompletionsClient(endpoint=self.endpoint, credential=AzureKeyCredential(self.token))

        try:
            response = await client.complete(
                messages=messages,
                model=self.model_name,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                top_p=self.top_p,
                frequency_penalty=self.frequency_penalty,
                presence_penalty=self.presence_penalty,
                stream=True,  # 这里强制流式
            )

            async for chunk in response:
                if chunk.choices and chunk["choices"][0]["delta"]:
                    yield chunk["choices"][0]["delta"]["content"]

        except HttpResponseError as e:
            logger.error(f"模型响应失败: {e.status_code} ({e.reason})")
            logger.error(f"{e.message}")
            yield f"模型响应失败: {e.status_code} ({e.reason})"
        finally:
            await client.close()

    @overload
    async def ask(
        self,
        prompt: str,
        history: List[Message],
        images: Optional[List[str]] = [],
        stream: Literal[False] = False,
        **kwargs,
    ) -> str: ...

    @overload
    async def ask(
        self,
        prompt: str,
        history: List[Message],
        images: Optional[List[str]] = [],
        stream: Literal[True] = True,
        **kwargs,
    ) -> AsyncGenerator[str, None]: ...

    async def ask(
        self,
        prompt: str,
        history: List[Message],
        images: Optional[List[str]] = [],
        stream: Optional[bool] = False,
        **kwargs,
    ) -> Union[AsyncGenerator[str, None], str]:
        messages = self._build_messages(prompt, history, images)

        if stream:
            return self._ask_stream(messages)

        return await self._ask_sync(messages)
